"""Frozen historical schema for revision 0001; do not use runtime models here."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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



def uuid_str() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Avatar(Base):
    __tablename__ = "avatars"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    emoji: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    student_number: Mapped[str | None] = mapped_column(String(64), unique=True)
    real_name: Mapped[str | None] = mapped_column(String(120))
    nickname: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    avatar_id: Mapped[str] = mapped_column(ForeignKey("avatars.id"), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.STUDENT, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_reset_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    avatar: Mapped[Avatar] = relationship()


class CourseRoster(Base, TimestampMixin):
    __tablename__ = "course_roster"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    student_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    real_name: Mapped[str] = mapped_column(String(120), nullable=False)
    section: Mapped[str | None] = mapped_column(String(80))
    registered_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    registered_user: Mapped[User | None] = relationship()


class JoinCode(Base, TimestampMixin):
    __tablename__ = "join_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stage: Mapped[TaskStage] = mapped_column(Enum(TaskStage), default=TaskStage.BASELINE_PRACTICE)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dev_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_official_submissions: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_zip_bytes: Mapped[int] = mapped_column(Integer, default=500_000_000, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=900, nullable=False)
    public_leaderboard_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    private_leaderboard_visible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evaluator_key: Mapped[str] = mapped_column(String(80), default="mock", nullable=False)

    config: Mapped["TaskConfig"] = relationship(back_populates="task", cascade="all, delete-orphan")


class TaskConfig(Base, TimestampMixin):
    __tablename__ = "task_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), unique=True, nullable=False)
    dataset_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    allowed_models: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    artifact_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    metric_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    split_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    scoring_strategy: Mapped[str] = mapped_column(String(80), default="task_primary_score", nullable=False)

    task: Mapped[Task] = relationship(back_populates="config")


class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("user_id", "task_id", "submission_number", name="uq_submission_number_per_task"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    kind: Mapped[SubmissionKind] = mapped_column(Enum(SubmissionKind), nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.UPLOADING, nullable=False
    )
    submission_number: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(160))
    base_model: Mapped[str | None] = mapped_column(String(160))
    seed: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    artifact_digest: Mapped[str | None] = mapped_column(String(64), index=True)
    validation_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    malware_scan_status: Mapped[str | None] = mapped_column(String(32))
    official_attempt_consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    safe_error_message: Mapped[str | None] = mapped_column(Text)
    internal_error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()
    task: Mapped[Task] = relationship()


class SubmissionFile(Base, TimestampMixin):
    __tablename__ = "submission_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))


class EvaluationJob(Base, TimestampMixin):
    __tablename__ = "evaluation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    split: Mapped[EvaluationSplit] = mapped_column(Enum(EvaluationSplit), nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.QUEUED, nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(120))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_kind: Mapped[str | None] = mapped_column(String(80))
    safe_error_message: Mapped[str | None] = mapped_column(Text)

    submission: Mapped[Submission] = relationship()


class Score(Base, TimestampMixin):
    __tablename__ = "scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    split: Mapped[EvaluationSplit] = mapped_column(Enum(EvaluationSplit), nullable=False)
    primary_metric: Mapped[str] = mapped_column(String(80), nullable=False)
    primary_score: Mapped[float] = mapped_column(nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    visible_to_student: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    submission: Mapped[Submission] = relationship()


class FinalSelection(Base, TimestampMixin):
    __tablename__ = "final_selections"
    __table_args__ = (UniqueConstraint("user_id", "task_id", name="uq_final_selection_per_task"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), nullable=False)


class LeaderboardSnapshot(Base, TimestampMixin):
    __tablename__ = "leaderboard_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    split: Mapped[EvaluationSplit] = mapped_column(Enum(EvaluationSplit), nullable=False)
    stage: Mapped[TaskStage | None] = mapped_column(Enum(TaskStage))
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)


class Announcement(Base, TimestampMixin):
    __tablename__ = "announcements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(120))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
