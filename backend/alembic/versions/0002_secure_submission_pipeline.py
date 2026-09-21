"""secure submission pipeline metadata

Revision ID: 0002_secure_submission_pipeline
Revises: 0001_initial
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_secure_submission_pipeline"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE submissionstatus ADD VALUE IF NOT EXISTS 'QUARANTINED'")

    inspector = sa.inspect(bind)
    task_config_columns = {column["name"] for column in inspector.get_columns("task_configs")}
    if "artifact_policy" not in task_config_columns:
        op.add_column(
            "task_configs",
            sa.Column("artifact_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )

    submission_columns = {column["name"] for column in inspector.get_columns("submissions")}
    additions = (
        ("artifact_digest", sa.Column("artifact_digest", sa.String(length=64), nullable=True)),
        (
            "validation_report",
            sa.Column("validation_report", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        ),
        ("malware_scan_status", sa.Column("malware_scan_status", sa.String(length=32), nullable=True)),
        ("internal_error_message", sa.Column("internal_error_message", sa.Text(), nullable=True)),
    )
    for name, column in additions:
        if name not in submission_columns:
            op.add_column("submissions", column)
    index_names = {index["name"] for index in inspector.get_indexes("submissions")}
    if "ix_submissions_artifact_digest" not in index_names:
        op.create_index("ix_submissions_artifact_digest", "submissions", ["artifact_digest"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    index_names = {index["name"] for index in inspector.get_indexes("submissions")}
    if "ix_submissions_artifact_digest" in index_names:
        op.drop_index("ix_submissions_artifact_digest", table_name="submissions")
    submission_columns = {column["name"] for column in inspector.get_columns("submissions")}
    for name in (
        "internal_error_message",
        "malware_scan_status",
        "validation_report",
        "artifact_digest",
    ):
        if name in submission_columns:
            op.drop_column("submissions", name)
    task_config_columns = {column["name"] for column in inspector.get_columns("task_configs")}
    if "artifact_policy" in task_config_columns:
        op.drop_column("task_configs", "artifact_policy")
    # PostgreSQL enum values are intentionally not removed during downgrade.
