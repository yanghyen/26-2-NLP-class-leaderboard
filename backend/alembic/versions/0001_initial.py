"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from pathlib import Path
    from runpy import run_path
    Base = run_path(str(Path(__file__).parents[1] / "initial_schema.py"))["Base"]

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from pathlib import Path
    from runpy import run_path
    Base = run_path(str(Path(__file__).parents[1] / "initial_schema.py"))["Base"]

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)

