import logging
import socket
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.enums import SubmissionStatus
from app.db.session import SessionLocal
from app.evaluators.base import EvaluationContext, EvaluationRequest, Evaluator
from app.evaluators.errors import EvaluatorError
from app.evaluators.registry import get_evaluator
from app.models import EvaluationJob, Score, Submission, Task
from app.queue import JobQueue, QueueUnavailableError, RedisJobQueue
from app.services.artifact_cleanup import cleanup_successful_artifacts, cleanup_successful_submission
from app.services.state import transition_job, transition_submission
from app.storage import LocalArtifactStorage
from app.storage.base import ArtifactStorage

logger = logging.getLogger(__name__)


class StudentArtifactError(ValueError):
    pass


class EvaluationTimeoutError(TimeoutError):
    pass


class JobOwnershipLost(RuntimeError):
    pass


def _owned_job(db: Session, job_id: str, attempt: int) -> EvaluationJob:
    job = db.scalar(select(EvaluationJob).where(EvaluationJob.id == job_id)
                    .with_for_update().execution_options(populate_existing=True))
    if job is None or job.attempts != attempt or job.status not in {
        SubmissionStatus.RUNNING, SubmissionStatus.SCORING,
    }:
        raise JobOwnershipLost
    db.refresh(job.submission)
    return job


def recover_jobs(*, db_factory=SessionLocal, queue: JobQueue,
                 now: datetime | None = None, limit: int = 100) -> None:
    """DB is the durable dispatch record; only expired attempts may be reclaimed.

    A 30s grace covers child termination and score commits after the hard deadline.
    The old attempt is fenced at scoring/commit even if its process resumes later.
    """
    now = now or datetime.now(UTC)
    with db_factory() as db:
        candidates = db.execute(select(EvaluationJob.id, EvaluationJob.locked_at, Task.timeout_seconds)
            .join(Submission, EvaluationJob.submission_id == Submission.id)
            .join(Task, Submission.task_id == Task.id)
            .where(EvaluationJob.status.in_([SubmissionStatus.RUNNING, SubmissionStatus.SCORING]))).all()
        recovered = 0
        for job_id, locked_at, timeout in candidates:
            if locked_at is not None:
                locked_at = locked_at.replace(tzinfo=UTC) if locked_at.tzinfo is None else locked_at
                if now < locked_at + timedelta(seconds=timeout + 30):
                    continue
            job = db.scalar(select(EvaluationJob).where(EvaluationJob.id == job_id)
                            .with_for_update().execution_options(populate_existing=True))
            if job.status not in {SubmissionStatus.RUNNING, SubmissionStatus.SCORING}:
                continue
            # Recheck after taking the row lock: another worker may have reclaimed it.
            current_lock = job.locked_at
            if current_lock is not None:
                current_lock = current_lock.replace(tzinfo=UTC) if current_lock.tzinfo is None else current_lock
                if now < current_lock + timedelta(seconds=timeout + 30):
                    continue
            if job.attempts >= job.max_attempts:
                _fail_without_retry(db, job, "WORKER_INTERRUPTED", "평가 작업이 중단되어 재시도 한도를 초과했습니다.")
            else:
                transition_job(job, SubmissionStatus.QUEUED)
                transition_submission(job.submission, SubmissionStatus.QUEUED)
                job.locked_at = None
                job.worker_id = None
                job.error_kind = "WORKER_INTERRUPTED_RETRY"
                job.safe_error_message = "중단된 평가를 다시 시도합니다."
                job.submission.safe_error_message = job.safe_error_message
                db.commit()
            recovered += 1
            if recovered >= limit:
                break
        # Includes crashes between BLPOP and claim, and between DB commit and RPUSH.
        ids = db.scalars(select(EvaluationJob.id).where(EvaluationJob.status == SubmissionStatus.QUEUED)
                         .order_by(EvaluationJob.created_at, EvaluationJob.id).limit(limit)).all()
    for job_id in ids:
        queue.enqueue(job_id)


def process_job(
    job_id: str,
    *,
    db_factory: Callable[[], Session] = SessionLocal,
    queue: JobQueue,
    storage: ArtifactStorage,
    evaluator_factory: Callable[[str], Evaluator] = get_evaluator,
    worker_id: str | None = None,
) -> None:
    db = db_factory()
    work_created = False
    attempt = None
    work_key = None
    try:
        # Conditional UPDATE claims exactly once, including concurrent consumers.
        claimed = db.execute(update(EvaluationJob).where(
            EvaluationJob.id == job_id, EvaluationJob.status == SubmissionStatus.QUEUED,
        ).values(status=SubmissionStatus.RUNNING, attempts=EvaluationJob.attempts + 1,
                 worker_id=worker_id or socket.gethostname(), locked_at=datetime.now(UTC)))
        if claimed.rowcount != 1:
            db.rollback()
            return
        job = db.get(EvaluationJob, job_id)
        attempt = job.attempts
        submission = job.submission
        if submission.status != SubmissionStatus.QUEUED or not submission.artifact_digest:
            _fail_without_retry(db, job, "INVALID_JOB_STATE", "평가할 수 없는 제출 상태입니다.")
            return
        task = submission.task
        transition_submission(submission, SubmissionStatus.RUNNING)
        db.commit()

        started = time.monotonic()
        work_key = f"{job.id}-{attempt}"
        # Reclaim scratch from dead attempts only after owning the retry.
        for previous in range(1, attempt):
            storage.delete_work_dir(f"{job.id}-{previous}")
        storage.delete_work_dir(job.id)  # legacy scratch layout
        work_path = storage.create_work_dir(work_key)
        work_created = True
        artifact_path = storage.artifact_path(submission.id)
        if not artifact_path.is_dir():
            raise StudentArtifactError("validated artifact is missing")

        def enter_scoring() -> None:
            _owned_job(db, job_id, attempt)
            transition_job(job, SubmissionStatus.SCORING)
            transition_submission(submission, SubmissionStatus.SCORING)
            db.commit()

        context = EvaluationContext(
            task_slug=task.slug,
            split=job.split.value,
            submission_dir=artifact_path / "model_artifact",
            dataset_config=task.config.dataset_config,
            allowed_models=task.config.allowed_models,
            metric_config=task.config.metric_config,
            artifact_digest=submission.artifact_digest,
            check_timeout=lambda: _check_timeout(started, task.timeout_seconds),
            on_scoring=enter_scoring,
            work_dir=work_path,
            deadline_monotonic=started + task.timeout_seconds,
        )
        metadata = deepcopy(submission.validation_report)
        model_metadata = metadata.get("model", {})
        manifest = model_metadata.get("manifest", {
            "base_model": model_metadata.get("base_model")
        })
        request = EvaluationRequest(
            submission_id=submission.id,
            task_id=task.id,
            evaluator_key=task.evaluator_key,
            artifact_path=artifact_path / "model_artifact",
            validated_manifest=manifest,
            validated_metadata=metadata,
            context=context,
        )
        evaluator = evaluator_factory(task.evaluator_key)
        try:
            result = evaluator.evaluate(request)
            _check_timeout(started, task.timeout_seconds)
            if job.status == SubmissionStatus.RUNNING:
                # A one-shot evaluator may return without an intermediate phase callback.
                enter_scoring()
            _owned_job(db, job_id, attempt)
            db.add(
                Score(
                    submission_id=submission.id,
                    split=job.split,
                    primary_metric=result.primary_metric,
                    primary_score=result.primary_score,
                    metrics=result.secondary_metrics,
                    visible_to_student=job.split.value != "PRIVATE",
                )
            )
            transition_job(job, SubmissionStatus.COMPLETED)
            transition_submission(submission, SubmissionStatus.COMPLETED)
            submission.completed_at = datetime.now(UTC)
            submission.evaluator_version = result.evaluator_version
            submission.dataset_version = result.dataset_version
            if result.evaluation_metadata:
                submission.validation_report = {**submission.validation_report, "evaluation": result.evaluation_metadata}
            submission.artifact_cleanup_status = "pending"
            job.error_kind = None
            job.safe_error_message = None
            submission.safe_error_message = None
            from app.services.results import pin_baseline
            pin_baseline(db, submission)
            db.commit()
            # Separate transaction; cleanup errors must never enter evaluation retry handling.
            try:
                cleanup_successful_submission(
                    submission.id, db_factory=db_factory, storage=storage
                )
            except Exception:
                logger.exception("Post-commit artifact cleanup failed: submission_id=%s", submission.id)
        finally:
            try:
                evaluator.cleanup(request)
            except Exception:
                logger.exception("Evaluator cleanup failed: job_id=%s", job_id)
    except JobOwnershipLost:
        db.rollback()
        logger.warning("Ignoring result from superseded attempt: job_id=%s attempt=%s", job_id, attempt)
    except EvaluatorError as exc:
        db.rollback()
        current = _current_attempt(db, job_id, attempt)
        if current is not None:
            _fail_without_retry(db, current, exc.code, str(exc))
    except (StudentArtifactError, EvaluationTimeoutError, KeyError, ValueError) as exc:
        db.rollback()
        current = _current_attempt(db, job_id, attempt)
        if current is not None and current.status in {
            SubmissionStatus.RUNNING,
            SubmissionStatus.SCORING,
        }:
            code = "EVALUATION_TIMEOUT" if isinstance(exc, EvaluationTimeoutError) else "STUDENT_ARTIFACT_ERROR"
            _fail_without_retry(db, current, code, "평가 시간 제한을 초과했습니다." if code == "EVALUATION_TIMEOUT" else "제출물을 평가할 수 없습니다.")
    except Exception as exc:
        db.rollback()
        logger.exception("Evaluation job failed with a server error: job_id=%s", job_id)
        current = _current_attempt(db, job_id, attempt)
        if current is not None:
            _retry_or_fail_server_error(db, current, queue, type(exc).__name__)
    finally:
        if work_created:
            try:
                storage.delete_work_dir(work_key)
            except Exception:
                logger.exception("Worker scratch cleanup failed: job_id=%s", job_id)
        db.close()


def run_worker_forever() -> None:
    queue = RedisJobQueue()
    storage = LocalArtifactStorage()
    worker_id = socket.gethostname()
    logger.info("Evaluation worker started with concurrency=1 worker_id=%s", worker_id)
    next_cleanup = 0.0
    while True:
        try:
            if time.monotonic() >= next_cleanup:
                recover_jobs(queue=queue)
                cleanup_successful_artifacts(storage=storage)
                next_cleanup = time.monotonic() + 30
            job_id = queue.dequeue(timeout=5)
            if job_id:
                process_job(job_id, queue=queue, storage=storage, worker_id=worker_id)
        except QueueUnavailableError:
            logger.exception("Evaluation queue is unavailable")
            time.sleep(1)
        except Exception:
            # A malformed job or unexpected failure must not terminate the next dequeue cycle.
            logger.exception("Unhandled worker cycle error")


def _check_timeout(started: float, timeout_seconds: int) -> None:
    if time.monotonic() - started > timeout_seconds:
        raise EvaluationTimeoutError


def _current_attempt(db: Session, job_id: str, attempt: int | None) -> EvaluationJob | None:
    if attempt is None:
        return None
    try:
        return _owned_job(db, job_id, attempt)
    except JobOwnershipLost:
        return None


def _fail_without_retry(db: Session, job: EvaluationJob, code: str, safe_message: str) -> None:
    submission = job.submission
    if job.status in {SubmissionStatus.QUEUED, SubmissionStatus.RUNNING, SubmissionStatus.SCORING}:
        transition_job(job, SubmissionStatus.FAILED)
    if submission.status in {
        SubmissionStatus.QUEUED,
        SubmissionStatus.RUNNING,
        SubmissionStatus.SCORING,
    }:
        transition_submission(submission, SubmissionStatus.FAILED)
    job.error_kind = code
    job.safe_error_message = safe_message
    submission.safe_error_message = safe_message
    db.commit()


def _retry_or_fail_server_error(
    db: Session, job: EvaluationJob, queue: JobQueue, internal_error: str
) -> None:
    submission = job.submission
    if job.status == SubmissionStatus.COMPLETED:
        return
    if job.attempts < job.max_attempts and job.status in {
        SubmissionStatus.RUNNING,
        SubmissionStatus.SCORING,
    }:
        transition_job(job, SubmissionStatus.QUEUED)
        transition_submission(submission, SubmissionStatus.QUEUED)
        job.error_kind = "SERVER_ERROR_RETRY"
        job.safe_error_message = "서버 오류로 평가를 다시 시도합니다."
        submission.safe_error_message = job.safe_error_message
        db.commit()
        try:
            queue.enqueue(job.id)
            return
        except QueueUnavailableError:
            db.refresh(job)
            db.refresh(submission)
    _fail_without_retry(db, job, "EVALUATION_FAILED", "서버 오류로 평가에 실패했습니다.")
    submission.official_attempt_consumed = False
    db.commit()
    logger.error("Job %s exhausted retry after %s", job.id, internal_error)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_worker_forever()


if __name__ == "__main__":
    main()
