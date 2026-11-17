"""Use ordered partial indexes for queue claims."""

from alembic import op
import sqlalchemy as sa

revision = "0002_queue_claim_indexes"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_judge_jobs_queued_available", table_name="judge_jobs")
    op.drop_index("ix_judge_jobs_stale_lease", table_name="judge_jobs")
    op.create_index(
        "ix_judge_jobs_queued_available",
        "judge_jobs",
        ["available_at", "id"],
        postgresql_where=sa.text("status = 'QUEUED'"),
    )
    op.create_index(
        "ix_judge_jobs_stale_lease",
        "judge_jobs",
        ["locked_at", "available_at", "id"],
        postgresql_where=sa.text("status = 'RUNNING'"),
    )


def downgrade() -> None:
    op.drop_index("ix_judge_jobs_queued_available", table_name="judge_jobs")
    op.drop_index("ix_judge_jobs_stale_lease", table_name="judge_jobs")
    op.create_index(
        "ix_judge_jobs_queued_available",
        "judge_jobs",
        ["available_at"],
        postgresql_where=sa.text("status = 'QUEUED'"),
    )
    op.create_index(
        "ix_judge_jobs_stale_lease",
        "judge_jobs",
        ["locked_at"],
        postgresql_where=sa.text("status = 'RUNNING'"),
    )
