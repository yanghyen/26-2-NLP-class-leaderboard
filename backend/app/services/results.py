from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Participant, Submission, Score, BaselineReference, Task
from app.core.enums import SubmissionStatus, SubmissionKind, EvaluationSplit


def utc_time(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def task_results(db: Session, task_id: str) -> list[dict]:
    results = []
    task = db.get(Task, task_id)
    deadline = (task.dev_deadline or task.final_deadline) if task else None
    for participant in db.scalars(select(Participant)).all():
        submissions = db.scalars(select(Submission).where(Submission.participant_id == participant.id, Submission.task_id == task_id)).all()
        if not submissions:
            continue
        pairs = db.execute(select(Submission, Score).join(Score, Score.submission_id == Submission.id).where(
            Submission.participant_id == participant.id, Submission.task_id == task_id,
            Submission.status == SubmissionStatus.COMPLETED, Score.visible_to_student.is_(True),
            Score.split.in_([EvaluationSplit.SMOKE, EvaluationSplit.PUBLIC]),
        ).order_by(Submission.completed_at, Submission.created_at, Submission.id)).all()
        if deadline:
            pairs = [pair for pair in pairs if utc_time(pair[0].completed_at or pair[0].created_at) <= utc_time(deadline)]
        reference = db.scalar(select(BaselineReference).where(BaselineReference.participant_id == participant.id, BaselineReference.task_id == task_id))
        baseline = next((pair for pair in pairs if reference and pair[0].id == reference.submission_id), None)
        developments = [pair for pair in pairs if pair[0].kind == SubmissionKind.EVALUATION and pair[1].split == EvaluationSplit.PUBLIC]
        best = max(developments, key=lambda pair: pair[1].primary_score, default=None)
        bs = baseline[1].primary_score if baseline else None
        ds = best[1].primary_score if best else None
        results.append(dict(participant=participant, representative=best or baseline,
            student_number=participant.roster_entry.student_number, nickname=participant.nickname, emoji=participant.emoji,
            baseline_score=bs, best_development_score=ds, improvement=ds-bs if ds is not None and bs is not None else None,
            total_submission_count=len(submissions), successful_submission_count=sum(x.status == SubmissionStatus.COMPLETED for x in submissions),
            failed_submission_count=sum(x.status == SubmissionStatus.FAILED for x in submissions),
            quarantined_submission_count=sum(x.status == SubmissionStatus.QUARANTINED for x in submissions),
            last_submitted_at=max(x.created_at for x in submissions)))
    return sorted(results, key=lambda row: row['student_number'])


def pin_baseline(db: Session, submission: Submission) -> None:
    if submission.participant_id and submission.kind == SubmissionKind.BASELINE_PRACTICE:
        exists = db.scalar(select(BaselineReference).where(BaselineReference.participant_id == submission.participant_id, BaselineReference.task_id == submission.task_id))
        if not exists:
            db.add(BaselineReference(participant_id=submission.participant_id, task_id=submission.task_id, submission_id=submission.id))
