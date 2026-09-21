from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import require_admin
from app.core.enums import SubmissionStatus
from app.models import CourseRoster, EvaluationJob, JoinCode, Submission, SubmissionFile, User
from app.queue import JobQueue, QueueUnavailableError, get_job_queue
from app.schemas import (
    EvaluationJobAdminOut,
    JoinCodeIn,
    JoinCodeOut,
    RosterRowOut,
    SubmissionAdminOut,
)
from app.services.audit import write_audit
from app.services.registration import create_join_code
from app.services.roster import parse_roster_csv, upsert_roster_rows
from app.services.state import InvalidStateTransition, transition_job, transition_submission
from app.storage import get_artifact_storage
from app.storage.base import ArtifactStorage

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/join-code", response_model=JoinCodeOut, status_code=status.HTTP_201_CREATED)
def set_join_code(
    payload: JoinCodeIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> JoinCode:
    join_code = create_join_code(
        db,
        label=payload.label,
        code=payload.code,
        deactivate_existing=payload.deactivate_existing,
    )
    write_audit(
        db,
        actor=actor,
        action="join_code.created",
        target_type="join_code",
        target_id=join_code.id,
        after={"label": join_code.label, "is_active": join_code.is_active},
    )
    db.commit()
    return join_code


@router.post("/roster/upload")
async def upload_roster(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> dict[str, int]:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV 파일만 업로드할 수 있습니다.")
    content = (await file.read()).decode("utf-8-sig")
    try:
        rows = parse_roster_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    count = upsert_roster_rows(db, rows)
    write_audit(
        db,
        actor=actor,
        action="roster.uploaded",
        target_type="course_roster",
        target_id=None,
        after={"count": count},
    )
    db.commit()
    return {"imported": count}


@router.get("/roster", response_model=list[RosterRowOut])
def list_roster(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[CourseRoster]:
    return list(db.scalars(select(CourseRoster).order_by(CourseRoster.student_number)).all())


@router.get("/submissions", response_model=list[SubmissionAdminOut])
def list_submissions(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[Submission]:
    return list(db.scalars(select(Submission).order_by(Submission.created_at.desc())).all())


@router.get("/jobs", response_model=list[EvaluationJobAdminOut])
def list_jobs(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[EvaluationJob]:
    return list(db.scalars(select(EvaluationJob).order_by(EvaluationJob.created_at.desc())).all())


@router.get("/quarantine", response_model=list[SubmissionAdminOut])
def list_quarantine(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[Submission]:
    return list(
        db.scalars(
            select(Submission)
            .where(Submission.status == SubmissionStatus.QUARANTINED)
            .order_by(Submission.created_at.desc())
        ).all()
    )


@router.get("/submissions/{submission_id}/download/{file_type}")
def download_submission_file(
    submission_id: str,
    file_type: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    storage: ArtifactStorage = Depends(get_artifact_storage),
) -> FileResponse:
    if file_type not in {"notebook", "model_zip"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    submission = db.get(Submission, submission_id)
    if submission is None or submission.status == SubmissionStatus.QUARANTINED:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    row = db.scalar(
        select(SubmissionFile).where(
            SubmissionFile.submission_id == submission_id,
            SubmissionFile.file_type == file_type,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    filename = "notebook.ipynb" if file_type == "notebook" else "model.zip"
    path = storage.artifact_path(submission_id) / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(path, filename=row.original_filename, media_type=row.mime_type)


@router.post("/jobs/{job_id}/retry", response_model=EvaluationJobAdminOut)
def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    queue: JobQueue = Depends(get_job_queue),
) -> EvaluationJob:
    job = db.get(EvaluationJob, job_id)
    if job is None or job.status != SubmissionStatus.FAILED or not job.error_kind:
        raise HTTPException(status_code=400, detail="재시도할 수 없는 Job입니다.")
    if job.error_kind not in {"EVALUATION_FAILED", "QUEUE_UNAVAILABLE", "SERVER_ERROR_RETRY"}:
        raise HTTPException(status_code=400, detail="학생 제출 오류는 자동 재시도하지 않습니다.")
    try:
        transition_job(job, SubmissionStatus.QUEUED)
        transition_submission(job.submission, SubmissionStatus.QUEUED)
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=400, detail="재시도할 수 없는 상태입니다.") from exc
    job.error_kind = None
    job.safe_error_message = None
    job.submission.safe_error_message = None
    db.commit()
    try:
        queue.enqueue(job.id)
    except QueueUnavailableError as exc:
        transition_job(job, SubmissionStatus.FAILED)
        transition_submission(job.submission, SubmissionStatus.FAILED)
        job.error_kind = "QUEUE_UNAVAILABLE"
        db.commit()
        raise HTTPException(status_code=503, detail="평가 대기열을 사용할 수 없습니다.") from exc
    write_audit(
        db,
        actor=actor,
        action="evaluation_job.retried",
        target_type="evaluation_job",
        target_id=job.id,
    )
    db.commit()
    db.refresh(job)
    return job


@router.post("/submissions/{submission_id}/invalidate", response_model=SubmissionAdminOut)
def invalidate_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> Submission:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="제출을 찾을 수 없습니다.")
    try:
        transition_submission(submission, SubmissionStatus.INVALIDATED)
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=400, detail="현재 상태에서는 무효화할 수 없습니다.") from exc
    write_audit(
        db,
        actor=actor,
        action="submission.invalidated",
        target_type="submission",
        target_id=submission.id,
    )
    db.commit()
    db.refresh(submission)
    return submission


@router.delete("/submissions/{submission_id}/artifact", status_code=status.HTTP_204_NO_CONTENT)
def delete_submission_artifact(
    submission_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    storage: ArtifactStorage = Depends(get_artifact_storage),
) -> None:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="제출을 찾을 수 없습니다.")
    if submission.status in PENDING_ADMIN_DELETE_STATUSES:
        raise HTTPException(status_code=400, detail="진행 중인 제출 artifact는 삭제할 수 없습니다.")
    storage.delete_artifact(submission.id)
    if submission.status != SubmissionStatus.INVALIDATED:
        transition_submission(submission, SubmissionStatus.INVALIDATED)
    write_audit(
        db,
        actor=actor,
        action="submission.artifact_deleted",
        target_type="submission",
        target_id=submission.id,
    )
    db.commit()


PENDING_ADMIN_DELETE_STATUSES = {
    SubmissionStatus.UPLOADING,
    SubmissionStatus.VALIDATING,
    SubmissionStatus.QUEUED,
    SubmissionStatus.RUNNING,
    SubmissionStatus.SCORING,
}
