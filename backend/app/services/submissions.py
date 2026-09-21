import hashlib
import logging
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import EvaluationSplit, MalwareScanStatus, SubmissionKind, SubmissionStatus
from app.models import EvaluationJob, Submission, SubmissionFile, Task, User
from app.queue import JobQueue, QueueUnavailableError
from app.schemas import SubmissionCreateIn
from app.security.malware import MalwareScanner
from app.security.validation import (
    ArtifactValidationError,
    ValidationResult,
    validate_and_extract_model_zip,
    validate_notebook,
)
from app.services.audit import write_audit
from app.services.state import transition_job, transition_submission
from app.storage.base import ArtifactStorage, UploadTooLargeError

logger = logging.getLogger(__name__)


class SubmissionError(ValueError):
    pass


class SubmissionUploadError(SubmissionError):
    def __init__(self, code: str, message: str, submission_id: str | None = None) -> None:
        self.code = code
        self.submission_id = submission_id
        super().__init__(message)


PENDING_STATUSES = {
    SubmissionStatus.UPLOADING,
    SubmissionStatus.VALIDATING,
    SubmissionStatus.QUEUED,
    SubmissionStatus.RUNNING,
    SubmissionStatus.SCORING,
}


async def create_submission_from_upload(
    db: Session,
    *,
    user: User,
    task: Task,
    payload: SubmissionCreateIn,
    notebook: UploadFile,
    model_zip: UploadFile,
    storage: ArtifactStorage,
    scanner: MalwareScanner,
    queue: JobQueue,
) -> tuple[Submission, EvaluationJob | None]:
    _check_upload_names(notebook, model_zip)
    _ensure_submission_allowed(db, user=user, task=task, kind=payload.kind)
    next_number = int(
        db.scalar(
            select(func.max(Submission.submission_number)).where(
                Submission.user_id == user.id, Submission.task_id == task.id
            )
        )
        or 0
    ) + 1
    submission = Submission(
        user_id=user.id,
        task_id=task.id,
        kind=payload.kind,
        status=SubmissionStatus.UPLOADING,
        submission_number=next_number,
        model_name=payload.model_name,
        base_model=payload.base_model,
        seed=payload.seed,
        metadata_json=payload.metadata_json,
        official_attempt_consumed=False,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    staging_id, staging_path = storage.create_staging_dir()
    notebook_path = staging_path / "notebook.ipynb"
    archive_path = staging_path / "model.zip"
    extracted_path = staging_path / "model_artifact"
    promoted = False
    try:
        settings = get_settings()
        notebook_size, notebook_hash = await storage.save_upload(
            notebook, notebook_path, settings.max_notebook_bytes
        )
        archive_size, archive_hash = await storage.save_upload(
            model_zip, archive_path, task.max_zip_bytes
        )
        transition_submission(submission, SubmissionStatus.VALIDATING)
        db.commit()

        notebook_report = validate_notebook(notebook_path, settings)
        archive_report, model_report = validate_and_extract_model_zip(
            archive_path,
            extracted_path,
            settings=settings,
            max_uncompressed_bytes=task.max_zip_bytes,
            allowed_models=task.config.allowed_models,
            artifact_policy=task.config.artifact_policy,
        )
        scan_result = scanner.scan([notebook_path, archive_path])
        submission.malware_scan_status = scan_result.status.value
        if scan_result.status in {MalwareScanStatus.INFECTED, MalwareScanStatus.SUSPICIOUS}:
            storage.quarantine(staging_id, submission.id)
            transition_submission(submission, SubmissionStatus.QUARANTINED)
            submission.safe_error_message = "안전 검사에서 제출물을 처리할 수 없습니다."
            submission.internal_error_message = scan_result.internal_detail
            submission.validation_report = {"error_code": "MALWARE_DETECTED"}
            write_audit(
                db,
                actor=user,
                action="submission.quarantined",
                target_type="submission",
                target_id=submission.id,
                after={"error_code": "MALWARE_DETECTED"},
            )
            db.commit()
            raise SubmissionUploadError(
                "MALWARE_DETECTED", submission.safe_error_message, submission.id
            )
        if scan_result.status == MalwareScanStatus.ERROR:
            raise ArtifactValidationError("VALIDATION_FAILED", "Malware scanner failed closed")

        artifact_digest = hashlib.sha256(
            f"{notebook_hash}:{archive_hash}".encode("ascii")
        ).hexdigest()
        report = ValidationResult(notebook_report, archive_report, model_report).public_report()
        storage.promote(staging_id, submission.id)
        promoted = True
        submission.artifact_digest = artifact_digest
        submission.validation_report = report
        submission.malware_scan_status = scan_result.status.value
        db.add_all(
            [
                SubmissionFile(
                    submission_id=submission.id,
                    file_type="notebook",
                    original_filename=_safe_display_name(notebook.filename),
                    storage_path=f"{submission.id}/notebook.ipynb",
                    size_bytes=notebook_size,
                    checksum_sha256=notebook_hash,
                    mime_type="application/x-ipynb+json",
                ),
                SubmissionFile(
                    submission_id=submission.id,
                    file_type="model_zip",
                    original_filename=_safe_display_name(model_zip.filename),
                    storage_path=f"{submission.id}/model.zip",
                    size_bytes=archive_size,
                    checksum_sha256=archive_hash,
                    mime_type="application/zip",
                ),
            ]
        )

        job = None
        if payload.kind == SubmissionKind.DRAFT:
            transition_submission(submission, SubmissionStatus.COMPLETED)
        else:
            split = (
                EvaluationSplit.SMOKE
                if payload.kind == SubmissionKind.BASELINE_PRACTICE
                else EvaluationSplit.PUBLIC
            )
            transition_submission(submission, SubmissionStatus.QUEUED)
            submission.official_attempt_consumed = payload.kind == SubmissionKind.EVALUATION
            job = EvaluationJob(
                submission_id=submission.id,
                split=split,
                status=SubmissionStatus.QUEUED,
                max_attempts=2,
            )
            db.add(job)
        db.commit()
        db.refresh(submission)
        if job is not None:
            db.refresh(job)
            try:
                queue.enqueue(job.id)
            except QueueUnavailableError as exc:
                transition_job(job, SubmissionStatus.FAILED)
                transition_submission(submission, SubmissionStatus.FAILED)
                job.error_kind = "QUEUE_UNAVAILABLE"
                job.safe_error_message = "평가 대기열 등록에 실패했습니다."
                submission.safe_error_message = job.safe_error_message
                submission.official_attempt_consumed = False
                db.commit()
                raise SubmissionUploadError(
                    "EVALUATION_FAILED", job.safe_error_message, submission.id
                ) from exc
        if payload.kind == SubmissionKind.DRAFT:
            _invalidate_old_drafts(db, user=user, task=task, keep=submission, storage=storage)
        return submission, job
    except SubmissionUploadError:
        raise
    except (ArtifactValidationError, UploadTooLargeError) as exc:
        _cleanup_failed_upload(storage, staging_id, submission.id, promoted)
        code = exc.code if isinstance(exc, ArtifactValidationError) else "MODEL_TOO_LARGE"
        _mark_validation_failed(db, submission, code, getattr(exc, "internal_detail", str(exc)))
        raise SubmissionUploadError(code, str(exc), submission.id) from exc
    except Exception as exc:
        _cleanup_failed_upload(storage, staging_id, submission.id, promoted)
        logger.exception("Submission validation failed for submission_id=%s", submission.id)
        _mark_validation_failed(db, submission, "VALIDATION_FAILED", type(exc).__name__)
        raise SubmissionUploadError(
            "VALIDATION_FAILED", "제출 파일 검증에 실패했습니다.", submission.id
        ) from exc


def _ensure_submission_allowed(
    db: Session, *, user: User, task: Task, kind: SubmissionKind
) -> None:
    if kind != SubmissionKind.DRAFT:
        pending = db.scalar(
            select(Submission).where(
                Submission.user_id == user.id,
                Submission.task_id == task.id,
                Submission.kind != SubmissionKind.DRAFT,
                Submission.status.in_(PENDING_STATUSES),
            )
        )
        if pending is not None:
            raise SubmissionError("이미 대기 중이거나 실행 중인 제출이 있습니다.")
    if kind == SubmissionKind.EVALUATION:
        consumed = db.scalar(
            select(func.count()).select_from(Submission).where(
                Submission.user_id == user.id,
                Submission.task_id == task.id,
                Submission.official_attempt_consumed.is_(True),
            )
        )
        if int(consumed or 0) >= task.max_official_submissions:
            raise SubmissionError("공식 제출 가능 횟수를 모두 사용했습니다.")


def _check_upload_names(notebook: UploadFile, model_zip: UploadFile) -> None:
    if not notebook.filename or Path(notebook.filename).suffix.lower() != ".ipynb":
        raise SubmissionError("Notebook은 .ipynb 파일이어야 합니다.")
    if not model_zip.filename or Path(model_zip.filename).suffix.lower() != ".zip":
        raise SubmissionError("모델 artifact는 .zip 파일이어야 합니다.")


def _safe_display_name(filename: str | None) -> str:
    name = Path((filename or "upload").replace("\x00", "")).name
    return name[:255] or "upload"


def _mark_validation_failed(
    db: Session, submission: Submission, code: str, internal_detail: str
) -> None:
    db.rollback()
    current = db.get(Submission, submission.id)
    if current is None:
        return
    if current.status in {SubmissionStatus.UPLOADING, SubmissionStatus.VALIDATING}:
        transition_submission(current, SubmissionStatus.FAILED)
    current.safe_error_message = {
        "INVALID_ARCHIVE": "모델 ZIP 형식이 올바르지 않습니다.",
        "UNSUPPORTED_FILE": "허용되지 않은 파일이 포함되어 있습니다.",
        "INVALID_MODEL_FORMAT": "모델 artifact 형식이 올바르지 않습니다.",
        "MODEL_TOO_LARGE": "제출 파일이 허용 제한을 초과했습니다.",
    }.get(code, "제출 파일 검증에 실패했습니다.")
    current.internal_error_message = internal_detail[:2_000]
    current.validation_report = {"error_code": code}
    current.official_attempt_consumed = False
    write_audit(
        db,
        actor=current.user,
        action="submission.validation_failed",
        target_type="submission",
        target_id=current.id,
        after={"error_code": code},
    )
    db.commit()


def _invalidate_old_drafts(
    db: Session,
    *,
    user: User,
    task: Task,
    keep: Submission,
    storage: ArtifactStorage,
) -> None:
    old_drafts = db.scalars(
        select(Submission).where(
            Submission.user_id == user.id,
            Submission.task_id == task.id,
            Submission.kind == SubmissionKind.DRAFT,
            Submission.id != keep.id,
            Submission.status == SubmissionStatus.COMPLETED,
        )
    ).all()
    for draft in old_drafts:
        transition_submission(draft, SubmissionStatus.INVALIDATED)
    if old_drafts:
        db.commit()
        for draft in old_drafts:
            storage.delete_artifact(draft.id)


def _cleanup_failed_upload(
    storage: ArtifactStorage, staging_id: str, submission_id: str, promoted: bool
) -> None:
    if promoted:
        storage.delete_artifact(submission_id)
    else:
        storage.delete_staging(staging_id)
