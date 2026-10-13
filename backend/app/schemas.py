from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import EvaluationSplit, SubmissionKind, SubmissionStatus, TaskStage, UserRole


class AvatarOut(BaseModel):
    id: str
    emoji: str
    label: str

    model_config = ConfigDict(from_attributes=True)


class LoginIn(BaseModel):
    student_number_or_nickname: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ErrorResponse(BaseModel):
    detail: str


class UserOut(BaseModel):
    id: str
    nickname: str
    avatar_id: str
    avatar_emoji: str
    role: UserRole
    student_number: str | None = None
    real_name: str | None = None
    password_reset_required: bool


class RosterRowOut(BaseModel):
    student_number: str
    real_name: str
    section: str | None
    participant_id: str | None = None
    nickname: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ArtifactPolicyIn(BaseModel):
    allowed_paths: list[str] | None = Field(default=None, min_length=1, max_length=256)
    allowed_architectures: list[str] = Field(min_length=1, max_length=64)
    allowed_dtypes: list[str] | None = Field(default=None, min_length=1, max_length=32)

    model_config = ConfigDict(extra="forbid")

    @field_validator("allowed_paths", "allowed_architectures", "allowed_dtypes")
    @classmethod
    def validate_unique_values(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("정책 목록에는 빈 값을 사용할 수 없습니다.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("정책 목록에는 중복 값을 사용할 수 없습니다.")
        return normalized


class TaskConfigIn(BaseModel):
    dataset_config: dict[str, Any] = Field(default_factory=dict)
    allowed_models: list[str] = Field(min_length=1, max_length=64)
    artifact_policy: ArtifactPolicyIn
    metric_config: dict[str, Any] = Field(default_factory=dict)
    split_config: dict[str, Any] = Field(default_factory=dict)
    scoring_strategy: str = "task_primary_score"

    @field_validator("allowed_models")
    @classmethod
    def validate_allowed_models(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("허용 base model에는 빈 값을 사용할 수 없습니다.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("허용 base model에는 중복 값을 사용할 수 없습니다.")
        return normalized


class TaskCreateIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
    title: str = Field(min_length=1, max_length=160)
    description: str = ""
    stage: TaskStage = TaskStage.BASELINE_PRACTICE
    is_public: bool = False
    max_official_submissions: int = Field(default=5, ge=0, le=100)
    max_zip_bytes: int = Field(default=500_000_000, ge=1_000_000)
    timeout_seconds: int = Field(default=900, ge=30)
    evaluator_key: str = "mock"
    opens_at: datetime | None = None
    dev_deadline: datetime | None = None
    final_deadline: datetime | None = None
    config: TaskConfigIn


class TaskConfigUpdateIn(BaseModel):
    dataset_config: dict[str, Any] | None = None
    allowed_models: list[str] | None = Field(default=None, min_length=1, max_length=64)
    artifact_policy: ArtifactPolicyIn | None = None
    metric_config: dict[str, Any] | None = None
    split_config: dict[str, Any] | None = None
    scoring_strategy: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("allowed_models")
    @classmethod
    def validate_allowed_models(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return TaskConfigIn.validate_allowed_models(values)


class TaskUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    stage: TaskStage | None = None
    is_public: bool | None = None
    max_official_submissions: int | None = Field(default=None, ge=0, le=100)
    max_zip_bytes: int | None = Field(default=None, ge=1_000_000)
    timeout_seconds: int | None = Field(default=None, ge=30)
    evaluator_key: str | None = Field(default=None, min_length=1, max_length=80)
    opens_at: datetime | None = None
    dev_deadline: datetime | None = None
    final_deadline: datetime | None = None
    config: TaskConfigUpdateIn | None = None

    @model_validator(mode="after")
    def reject_empty_update(self) -> "TaskUpdateIn":
        if not self.model_fields_set:
            raise ValueError("수정할 필드를 하나 이상 전달해야 합니다.")
        if self.config is not None and not self.config.model_fields_set:
            raise ValueError("빈 config로 정책을 덮어쓸 수 없습니다.")
        return self


class TaskOut(BaseModel):
    id: str
    slug: str
    title: str
    description: str
    stage: TaskStage
    is_public: bool
    max_official_submissions: int
    max_zip_bytes: int
    timeout_seconds: int
    evaluator_key: str
    opens_at: datetime | None
    dev_deadline: datetime | None
    final_deadline: datetime | None
    public_leaderboard_visible: bool
    private_leaderboard_visible: bool

    model_config = ConfigDict(from_attributes=True)


class TaskConfigOut(BaseModel):
    dataset_config: dict[str, Any]
    allowed_models: list[str]
    artifact_policy: dict[str, Any]
    metric_config: dict[str, Any]
    split_config: dict[str, Any]
    scoring_strategy: str

    model_config = ConfigDict(from_attributes=True)


class TaskDetailOut(TaskOut):
    config: TaskConfigOut


class SubmissionCreateIn(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    kind: SubmissionKind = SubmissionKind.EVALUATION
    model_name: str | None = Field(default=None, max_length=160)
    base_model: str | None = Field(default=None, max_length=160)
    seed: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    task_id: str
    kind: SubmissionKind
    status: SubmissionStatus
    model_name: str | None
    safe_error_message: str | None
    created_at: datetime


class ScoreOut(BaseModel):
    split: EvaluationSplit
    primary_metric: str
    primary_score: float
    metrics: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class SubmissionFileOut(BaseModel):
    file_type: str
    original_filename: str
    size_bytes: int
    checksum_sha256: str

    model_config = ConfigDict(from_attributes=True)


class SubmissionDetailOut(SubmissionOut):
    scores: list[ScoreOut] = Field(default_factory=list)
    files: list[SubmissionFileOut] = Field(default_factory=list)


class SubmissionAdminOut(SubmissionOut):
    artifact_cleanup_status: str
    artifact_deleted_at: datetime | None
    evaluator_version: str | None
    dataset_version: str | None
    submission_number: int
    base_model: str | None
    seed: int | None
    official_attempt_consumed: bool
    user_id: str | None = None
    participant_id: str | None = None
    student_number: str | None = None
    nickname: str = ""
    task_slug: str = ""
    task_title: str = ""
    artifact_digest: str | None
    validation_report: dict[str, Any]
    malware_scan_status: str | None
    internal_error_message: str | None


class EvaluationJobOut(BaseModel):
    id: str
    submission_id: str
    split: EvaluationSplit
    status: SubmissionStatus
    attempts: int
    max_attempts: int

    model_config = ConfigDict(from_attributes=True)


class EvaluationJobAdminOut(EvaluationJobOut):
    worker_id: str | None
    error_kind: str | None
    safe_error_message: str | None


class SubmissionCreateOut(BaseModel):
    submission: SubmissionOut
    evaluation_job: EvaluationJobOut | None


class LeaderboardRowOut(BaseModel):
    baseline_score: float | None = None
    best_development_score: float | None = None
    improvement: float | None = None
    model_config = ConfigDict(protected_namespaces=())

    rank: int
    nickname: str
    avatar_id: str
    avatar_emoji: str
    primary_metric: str
    primary_score: float
    metrics: dict[str, Any]
    model_name: str | None
    submitted_at: datetime


class PublicTaskConfigOut(BaseModel):
    allowed_models: list[str]
    artifact_policy: dict[str, Any]
    model_config = ConfigDict(from_attributes=True)


class PublicTaskOut(TaskOut):
    max_official_submissions: int = Field(exclude=True)


class PublicTaskDetailOut(PublicTaskOut):
    config: PublicTaskConfigOut
