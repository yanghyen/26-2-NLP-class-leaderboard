"""Track post-commit artifact cleanup and preserve evaluation versions."""
from alembic import op
import sqlalchemy as sa

revision = "0005_successful_artifact_cleanup"
down_revision = "0004_roster_participants"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("submissions", sa.Column(
        "artifact_cleanup_status", sa.String(16), server_default="retained", nullable=False
    ))
    op.add_column("submissions", sa.Column("artifact_deleted_at", sa.DateTime(timezone=True)))
    op.add_column("submissions", sa.Column("evaluator_version", sa.String(120)))
    op.add_column("submissions", sa.Column("dataset_version", sa.Text()))
    op.create_index("ix_submissions_artifact_cleanup_status", "submissions", ["artifact_cleanup_status"])
    # Existing evaluated submissions are recovered by the same guarded cleanup sweep.
    # Do not invent historical evaluator/dataset versions or delete files in a migration.


def downgrade():
    op.drop_index("ix_submissions_artifact_cleanup_status", table_name="submissions")
    with op.batch_alter_table("submissions") as batch:
        for column in ("dataset_version", "evaluator_version", "artifact_deleted_at", "artifact_cleanup_status"):
            batch.drop_column(column)
