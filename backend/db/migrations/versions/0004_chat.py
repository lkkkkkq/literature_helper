"""Project model metadata and isolated question/answer history; no credentials."""

import sqlalchemy as sa
from alembic import op

revision = "0004_chat"
down_revision = "0003_parsed_assets"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "model_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
    )
    op.create_table(
        "chat_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("answer", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.UniqueConstraint("project_id", "request_id"),
        sa.ForeignKeyConstraint(
            ["project_id", "session_id"],
            ["chat_sessions.project_id", "chat_sessions.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_chat_runs_project_id", "chat_runs", ["project_id"])


def downgrade():
    op.drop_table("chat_runs")
    op.drop_table("model_profiles")
