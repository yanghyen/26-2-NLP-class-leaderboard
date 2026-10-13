"""Separate authentication from participants; retain unmatched legacy submissions.

Revision ID: 0004_roster_participants
Revises: 0003_backfill_test_task_policy
"""
import uuid
import sqlalchemy as sa
from alembic import op
revision = "0004_roster_participants"
down_revision = "0003_backfill_test_task_policy"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("participants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("roster_entry_id", sa.String(36), sa.ForeignKey("course_roster.id"), nullable=False, unique=True),
        sa.Column("nickname", sa.String(16), nullable=False), sa.Column("emoji", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    with op.batch_alter_table("submissions") as batch:
        batch.alter_column("user_id", existing_type=sa.String(36), nullable=True)
        batch.add_column(sa.Column("participant_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_submission_participant", "participants", ["participant_id"], ["id"])
        batch.create_unique_constraint("uq_participant_submission_number", ["participant_id", "task_id", "submission_number"])
        batch.drop_constraint("uq_submission_number_per_task", type_="unique")
    op.create_table("baseline_references",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("participant_id", sa.String(36), sa.ForeignKey("participants.id"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("submission_id", sa.String(36), sa.ForeignKey("submissions.id"), nullable=False),
        sa.UniqueConstraint("participant_id", "task_id", name="uq_baseline_reference"))
    bind = op.get_bind()
    metadata = sa.MetaData()
    users, roster, avatars, participants, submissions, scores, references = [sa.Table(name, metadata, autoload_with=bind) for name in
        ["users", "course_roster", "avatars", "participants", "submissions", "scores", "baseline_references"]]
    # Only authoritative, consistent roster links. Never infer from names or invent roster entries.
    rows = bind.execute(sa.select(roster.c.id, users.c.id.label("user_id"), users.c.nickname, avatars.c.emoji)
        .join(users, users.c.id == roster.c.registered_user_id).join(avatars, avatars.c.id == users.c.avatar_id)
        .where(users.c.role == "STUDENT", users.c.student_number == roster.c.student_number)).mappings().all()
    for row in rows:
        pid = str(uuid.uuid4())
        bind.execute(participants.insert().values(id=pid, roster_entry_id=row["id"], nickname=row["nickname"], emoji=row["emoji"]))
        bind.execute(submissions.update().where(submissions.c.user_id == row["user_id"]).values(participant_id=pid))
        successful = bind.execute(sa.select(submissions.c.id, submissions.c.task_id)
            .join(scores, scores.c.submission_id == submissions.c.id)
            .where(submissions.c.participant_id == pid, submissions.c.kind == "BASELINE_PRACTICE",
                   submissions.c.status == "COMPLETED", scores.c.split == "SMOKE", scores.c.visible_to_student.is_(True))
            .order_by(submissions.c.completed_at, submissions.c.created_at, submissions.c.id)).mappings().all()
        seen = set()
        for submission in successful:
            if submission["task_id"] not in seen:
                bind.execute(references.insert().values(id=str(uuid.uuid4()), participant_id=pid, task_id=submission["task_id"], submission_id=submission["id"]))
                seen.add(submission["task_id"])
    # Preserve rows/foreign keys for audit but permanently disable student credentials.
    bind.execute(users.update().where(users.c.role == "STUDENT").values(is_active=False, password_hash="!disabled-student-auth"))


def downgrade():
    raise RuntimeError("Forward-only migration: new submissions have no User. Restore a verified backup to roll back.")
