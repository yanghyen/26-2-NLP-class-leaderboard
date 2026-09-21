from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.enums import EvaluationSplit, SubmissionKind, SubmissionStatus
from app.models import EvaluationJob, Submission, Task, User
from app.schemas import SubmissionCreateIn


class SubmissionError(ValueError):
    pass


PENDING_STATUSES = {
    SubmissionStatus.UPLOADING,
    SubmissionStatus.VALIDATING,
    SubmissionStatus.QUEUED,
    SubmissionStatus.RUNNING,
    SubmissionStatus.SCORING,
}


def create_submission_record(
    db: Session, *, user: User, task: Task, payload: SubmissionCreateIn
) -> tuple[Submission, EvaluationJob | None]:
    pending = db.scalar(
        select(Submission).where(
            Submission.user_id == user.id,
            Submission.task_id == task.id,
            Submission.status.in_(PENDING_STATUSES),
        )
    )
    if pending is not None and payload.kind != SubmissionKind.DRAFT:
        raise SubmissionError("이미 대기 중이거나 실행 중인 제출이 있습니다.")

    current_count = db.scalar(
        select(func.count()).select_from(Submission).where(
            Submission.user_id == user.id,
            Submission.task_id == task.id,
            Submission.kind != SubmissionKind.DRAFT,
        )
    )
    submission_number = int(current_count or 0) + 1
    official_attempt = payload.kind == SubmissionKind.EVALUATION
    if official_attempt:
        consumed = db.scalar(
            select(func.count()).select_from(Submission).where(
                Submission.user_id == user.id,
                Submission.task_id == task.id,
                Submission.official_attempt_consumed.is_(True),
            )
        )
        if int(consumed or 0) >= task.max_official_submissions:
            raise SubmissionError("공식 제출 가능 횟수를 모두 사용했습니다.")

    status = SubmissionStatus.UPLOADING if payload.kind == SubmissionKind.DRAFT else SubmissionStatus.QUEUED
    submission = Submission(
        user_id=user.id,
        task_id=task.id,
        kind=payload.kind,
        status=status,
        submission_number=submission_number,
        model_name=payload.model_name,
        base_model=payload.base_model,
        seed=payload.seed,
        metadata_json=payload.metadata_json,
        official_attempt_consumed=official_attempt,
    )
    db.add(submission)
    db.flush()

    job = None
    if payload.kind != SubmissionKind.DRAFT:
        split = (
            EvaluationSplit.SMOKE
            if payload.kind == SubmissionKind.BASELINE_PRACTICE
            else EvaluationSplit.PUBLIC
        )
        job = EvaluationJob(
            submission_id=submission.id,
            split=split,
            status=SubmissionStatus.QUEUED,
            max_attempts=2,
        )
        db.add(job)
    db.commit()
    db.refresh(submission)
    if job:
        db.refresh(job)
    return submission, job

