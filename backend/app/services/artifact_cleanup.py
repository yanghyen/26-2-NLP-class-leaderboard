"""Idempotent cleanup using a fresh session to inspect committed evaluation results."""
import logging
from datetime import UTC, datetime
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import SubmissionKind, SubmissionStatus
from app.db.session import SessionLocal
from app.models import EvaluationJob, Score, Submission
from app.services.audit import write_audit
from app.storage.base import ArtifactStorage

logger = logging.getLogger(__name__)


def _eligible():
    return (
        Submission.status == SubmissionStatus.COMPLETED,
        Submission.kind.in_([SubmissionKind.BASELINE_PRACTICE, SubmissionKind.EVALUATION]),
        Submission.malware_scan_status.not_in(["INFECTED", "SUSPICIOUS", "ERROR"])
        | Submission.malware_scan_status.is_(None),
        select(Score.id).where(Score.submission_id == Submission.id).exists(),
        select(EvaluationJob.id).where(
            EvaluationJob.submission_id == Submission.id,
            EvaluationJob.status == SubmissionStatus.COMPLETED,
        ).exists(),
    )


def cleanup_successful_submission(
    submission_id: str,
    *,
    storage: ArtifactStorage,
    db_factory: Callable[[], Session] = SessionLocal,
) -> bool:
    """Delete only committed successes; missing files succeed; failures remain pending.

    The caller must commit the evaluation transaction before invoking this function.
    A separate session never commits any of the caller's evaluation changes.
    """
    with db_factory() as db:
        submission = db.scalar(select(Submission).where(
            Submission.id == submission_id, *_eligible()
        ).with_for_update())
        if submission is None:
            return False
        if submission.artifact_cleanup_status == "deleted":
            return True
        submission.artifact_cleanup_status = "pending"
        try:
            storage.delete_artifact(submission.id)
        except Exception:
            # Only a fixed code reaches DB/API audit; exception details stay in server logs.
            logger.exception("Artifact cleanup pending: submission_id=%s", submission_id)
            write_audit(db, actor=None, action="submission.artifact_cleanup_pending",
                        target_type="submission", target_id=submission_id,
                        after={"code": "ARTIFACT_CLEANUP_FAILED"})
            submission.updated_at = datetime.now(UTC)
            db.commit()
            return False
        submission.artifact_cleanup_status = "deleted"
        submission.artifact_deleted_at = datetime.now(UTC)
        write_audit(db, actor=None, action="submission.artifact_auto_deleted",
                    target_type="submission", target_id=submission_id)
        db.commit()
        return True


def cleanup_successful_artifacts(
    *,
    storage: ArtifactStorage,
    db_factory: Callable[[], Session] = SessionLocal,
    limit: int = 100,
) -> int:
    """Bounded recovery sweep, including successes from before the retention policy.

    Oldest updated rows first keep repeatedly failing deletions from starving others.
    Each submission uses its own transaction so one failure does not stop the batch.
    """
    with db_factory() as db:
        ids = list(db.scalars(select(Submission.id).where(
            *_eligible(), Submission.artifact_cleanup_status != "deleted"
        ).order_by(Submission.updated_at, Submission.id).limit(limit)))
    deleted = 0
    for submission_id in ids:
        try:
            deleted += cleanup_successful_submission(
                submission_id, storage=storage, db_factory=db_factory
            )
        except Exception:
            logger.exception("Artifact cleanup transaction failed: submission_id=%s", submission_id)
    return deleted
