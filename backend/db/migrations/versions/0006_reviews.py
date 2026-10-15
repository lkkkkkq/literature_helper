"""Append-only field revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0006_reviews"
down_revision = "0005_jobs"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "review_revisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("extraction_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("record_id", sa.String(), nullable=False),
        sa.Column("field_key", sa.String(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.UniqueConstraint("job_id", "version"),
    )


def downgrade():
    op.drop_table("review_revisions")
