from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import EvaluationSplit, SubmissionKind, SubmissionStatus, TaskStage, UserRole


class AvatarOut(BaseModel):
    id: str
    emoji: str
    label: str

    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    student_number: str = Field(min_length=1, max_length=64)
    real_name: str = Field(min_length=1, max_length=120)
    nickname: str = Field(min_length=2, max_length=16)
    avatar_id: str
    password: str = Field(min_length=8, max_length=128)
    join_code: str = Field(min_length=1, max_length=120)


class LoginIn(BaseModel):
    student_number_or_nickname: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PublicProfile(BaseModel):
    nickname: str
    avatar_id: str
    avatar_emoji: str


class UserOut(BaseModel):
    id: str
    nickname: str
    avatar_id: str
    avatar_emoji: str
    role: UserRole
    student_number: str | None = None
    real_name: str | None = None
    password_reset_required: bool


class JoinCodeIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=6, max_length=120)
    deactivate_existing: bool = True


class JoinCodeOut(BaseModel):
    id: str
    label: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RosterRowOut(BaseModel):
    student_number: str
    real_name: str
    section: str | None
    registered_user_id: str | None

    model_config = ConfigDict(from_attributes=True)


class TaskConfigIn(BaseModel):
    dataset_config: dict[str, Any] = Field(default_factory=dict)
    allowed_models: list[str] = Field(default_factory=list)
    metric_config: dict[str, Any] = Field(default_factory=dict)
    split_config: dict[str, Any] = Field(default_factory=dict)
    scoring_strategy: str = "task_primary_score"


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
    config: TaskConfigIn = Field(default_factory=TaskConfigIn)


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

    model_config = ConfigDict(from_attributes=True)


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
    submission_number: int
    model_name: str | None
    base_model: str | None
    seed: int | None
    official_attempt_consumed: bool
    safe_error_message: str | None
    created_at: datetime


class EvaluationJobOut(BaseModel):
    id: str
    submission_id: str
    split: EvaluationSplit
    status: SubmissionStatus
    attempts: int
    max_attempts: int

    model_config = ConfigDict(from_attributes=True)
