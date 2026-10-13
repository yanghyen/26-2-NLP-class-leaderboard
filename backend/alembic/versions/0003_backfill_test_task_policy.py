"""backfill the canonical development test task policy

Revision ID: 0003_backfill_test_task_policy
Revises: 0002_secure_submission_pipeline
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_backfill_test_task_policy"
down_revision: str | None = "0002_secure_submission_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALLOWED_MODELS = ["course/bert-base"]
_ARTIFACT_POLICY = {"allowed_architectures": ["BertForSequenceClassification"]}


def _tables(bind: sa.Connection) -> tuple[sa.Table, sa.Table]:
    metadata = sa.MetaData()
    tasks = sa.Table("tasks", metadata, autoload_with=bind)
    configs = sa.Table("task_configs", metadata, autoload_with=bind)
    return tasks, configs


def upgrade() -> None:
    bind = op.get_bind()
    tasks, configs = _tables(bind)
    rows = bind.execute(
        sa.select(configs.c.id, configs.c.allowed_models, configs.c.artifact_policy)
        .join(tasks, tasks.c.id == configs.c.task_id)
        .where(tasks.c.slug == "test")
    ).mappings()
    for row in rows:
        if row["allowed_models"] == _ALLOWED_MODELS and not row["artifact_policy"]:
            bind.execute(
                configs.update()
                .where(configs.c.id == row["id"])
                .values(artifact_policy=_ARTIFACT_POLICY)
            )


def downgrade() -> None:
    bind = op.get_bind()
    tasks, configs = _tables(bind)
    rows = bind.execute(
        sa.select(configs.c.id, configs.c.allowed_models, configs.c.artifact_policy)
        .join(tasks, tasks.c.id == configs.c.task_id)
        .where(tasks.c.slug == "test")
    ).mappings()
    for row in rows:
        if (
            row["allowed_models"] == _ALLOWED_MODELS
            and row["artifact_policy"] == _ARTIFACT_POLICY
        ):
            bind.execute(
                configs.update().where(configs.c.id == row["id"]).values(artifact_policy={})
            )
