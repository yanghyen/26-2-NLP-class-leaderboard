from enum import StrEnum


class UserRole(StrEnum):
    STUDENT = "STUDENT"
    ADMIN = "ADMIN"


class TaskStage(StrEnum):
    BASELINE_PRACTICE = "BASELINE_PRACTICE"
    DEVELOPMENT = "DEVELOPMENT"
    FINAL = "FINAL"


class SubmissionKind(StrEnum):
    DRAFT = "DRAFT"
    EVALUATION = "EVALUATION"
    BASELINE_PRACTICE = "BASELINE_PRACTICE"


class SubmissionStatus(StrEnum):
    UPLOADING = "UPLOADING"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SCORING = "SCORING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"
    INVALIDATED = "INVALIDATED"


class EvaluationSplit(StrEnum):
    SMOKE = "SMOKE"
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"


class MalwareScanStatus(StrEnum):
    DISABLED = "DISABLED"
    CLEAN = "CLEAN"
    INFECTED = "INFECTED"
    SUSPICIOUS = "SUSPICIOUS"
    ERROR = "ERROR"
