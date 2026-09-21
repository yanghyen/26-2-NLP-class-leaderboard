from app.core.enums import SubmissionStatus
from app.models import EvaluationJob, Submission


class InvalidStateTransition(ValueError):
    pass


SUBMISSION_TRANSITIONS: dict[SubmissionStatus, set[SubmissionStatus]] = {
    SubmissionStatus.UPLOADING: {SubmissionStatus.VALIDATING, SubmissionStatus.FAILED},
    SubmissionStatus.VALIDATING: {
        SubmissionStatus.QUEUED,
        SubmissionStatus.COMPLETED,
        SubmissionStatus.FAILED,
        SubmissionStatus.QUARANTINED,
    },
    SubmissionStatus.QUEUED: {
        SubmissionStatus.RUNNING,
        SubmissionStatus.FAILED,
        SubmissionStatus.INVALIDATED,
    },
    SubmissionStatus.RUNNING: {
        SubmissionStatus.QUEUED,
        SubmissionStatus.SCORING,
        SubmissionStatus.FAILED,
    },
    SubmissionStatus.SCORING: {SubmissionStatus.COMPLETED, SubmissionStatus.FAILED},
    SubmissionStatus.COMPLETED: {SubmissionStatus.INVALIDATED},
    SubmissionStatus.FAILED: {SubmissionStatus.QUEUED, SubmissionStatus.INVALIDATED},
    SubmissionStatus.QUARANTINED: {SubmissionStatus.INVALIDATED},
    SubmissionStatus.INVALIDATED: set(),
}

JOB_TRANSITIONS: dict[SubmissionStatus, set[SubmissionStatus]] = {
    SubmissionStatus.QUEUED: {SubmissionStatus.RUNNING, SubmissionStatus.FAILED},
    SubmissionStatus.RUNNING: {
        SubmissionStatus.QUEUED,
        SubmissionStatus.SCORING,
        SubmissionStatus.FAILED,
    },
    SubmissionStatus.SCORING: {SubmissionStatus.COMPLETED, SubmissionStatus.FAILED},
    SubmissionStatus.FAILED: {SubmissionStatus.QUEUED},
    SubmissionStatus.COMPLETED: set(),
}


def transition_submission(submission: Submission, target: SubmissionStatus) -> None:
    if target not in SUBMISSION_TRANSITIONS.get(submission.status, set()):
        raise InvalidStateTransition(f"submission {submission.status} -> {target} is not allowed")
    submission.status = target


def transition_job(job: EvaluationJob, target: SubmissionStatus) -> None:
    if target not in JOB_TRANSITIONS.get(job.status, set()):
        raise InvalidStateTransition(f"job {job.status} -> {target} is not allowed")
    job.status = target
