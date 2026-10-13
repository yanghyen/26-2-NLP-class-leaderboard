import logging
import socket
import time
from datetime import UTC, datetime
from typing import Callable

from sqlalchemy.orm import Session

from app.core.enums import SubmissionStatus
from app.db.session import SessionLocal
from app.evaluators.base import EvaluationContext, Evaluator
from app.evaluators.registry import get_evaluator
from app.models import EvaluationJob, Score
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
    try:
        job = db.get(EvaluationJob, job_id)
        if job is None or job.status != SubmissionStatus.QUEUED:
            return
        submission = job.submission
        if submission.status != SubmissionStatus.QUEUED or not submission.artifact_digest:
            _fail_without_retry(db, job, "INVALID_JOB_STATE", "평가할 수 없는 제출 상태입니다.")
            return
        task = submission.task
        job.attempts += 1
        job.worker_id = worker_id or socket.gethostname()
        job.locked_at = datetime.now(UTC)
        transition_job(job, SubmissionStatus.RUNNING)
        transition_submission(submission, SubmissionStatus.RUNNING)
        db.commit()

        started = time.monotonic()
        storage.create_work_dir(job.id)
        work_created = True
        artifact_path = storage.artifact_path(submission.id)
        if not artifact_path.is_dir():
            raise StudentArtifactError("validated artifact is missing")
        context = EvaluationContext(
            task_slug=task.slug,
            split=job.split.value,
            submission_dir=artifact_path / "model_artifact",
            dataset_config=task.config.dataset_config,
            allowed_models=task.config.allowed_models,
            metric_config=task.config.metric_config,
            artifact_digest=submission.artifact_digest,
        )
        evaluator = evaluator_factory(task.evaluator_key)
        try:
            evaluator.validate_submission(context)
            prepared = evaluator.prepare(context)
            predictions = evaluator.run_inference(context, prepared)
            _check_timeout(started, task.timeout_seconds)
            transition_job(job, SubmissionStatus.SCORING)
            transition_submission(submission, SubmissionStatus.SCORING)
            db.commit()
            result = evaluator.format_result(evaluator.compute_metrics(context, predictions))
            _check_timeout(started, task.timeout_seconds)
            db.add(
                Score(
                    submission_id=submission.id,
                    split=job.split,
                    primary_metric=str(result["primary_metric"]),
                    primary_score=float(result["primary_score"]),
                    metrics=dict(result.get("metrics", {})),
                    visible_to_student=job.split.value != "PRIVATE",
                )
            )
            transition_job(job, SubmissionStatus.COMPLETED)
            transition_submission(submission, SubmissionStatus.COMPLETED)
            submission.completed_at = datetime.now(UTC)
            submission.evaluator_version = evaluator.version
            dataset_version = context.dataset_config.get(
                "dataset_version", context.dataset_config.get("version")
            )
            submission.dataset_version = str(dataset_version) if dataset_version is not None else None
            submission.artifact_cleanup_status = "pending"
            job.error_kind = None
            job.safe_error_message = None
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
                evaluator.cleanup(context)
            except Exception:
                logger.exception("Evaluator cleanup failed: job_id=%s", job_id)
    except (StudentArtifactError, EvaluationTimeoutError, KeyError, ValueError) as exc:
        db.rollback()
        current = db.get(EvaluationJob, job_id)
        if current is not None and current.status in {
            SubmissionStatus.RUNNING,
            SubmissionStatus.SCORING,
        }:
            code = "EVALUATION_TIMEOUT" if isinstance(exc, EvaluationTimeoutError) else "STUDENT_ARTIFACT_ERROR"
            _fail_without_retry(db, current, code, "평가 시간 제한을 초과했습니다." if code == "EVALUATION_TIMEOUT" else "제출물을 평가할 수 없습니다.")
    except Exception as exc:
        db.rollback()
        logger.exception("Evaluation job failed with a server error: job_id=%s", job_id)
        current = db.get(EvaluationJob, job_id)
        if current is not None:
            _retry_or_fail_server_error(db, current, queue, type(exc).__name__)
    finally:
        if work_created:
            try:
                storage.delete_work_dir(job_id)
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
