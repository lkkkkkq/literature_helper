"""Versioned plans, SQLite job queue, per-document progress and automatic records."""

import sqlalchemy as sa
from alembic import op

revision = "0005_jobs"
down_revision = "0004_chat"
branch_labels = None
depends_on = None


def common():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
    ]


def session_fk():
    return sa.ForeignKeyConstraint(
        ["project_id", "session_id"],
        ["chat_sessions.project_id", "chat_sessions.id"],
        ondelete="CASCADE",
    )


def upgrade():
    op.create_table(
        "extraction_schemas",
        *common(),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("goal", sa.String(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        session_fk(),
    )
    op.create_table(
        "extraction_jobs",
        *common(),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column(
            "schema_id",
            sa.String(),
            sa.ForeignKey("extraction_schemas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.UniqueConstraint("project_id", "request_id"),
        session_fk(),
    )
    op.create_table(
        "job_documents",
        *common(),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("extraction_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("fingerprints", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.UniqueConstraint("job_id", "document_id"),
    )
    op.create_table(
        "records",
        *common(),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("extraction_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("values_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    for table in ["extraction_schemas", "extraction_jobs", "job_documents", "records"]:
        op.create_index(f"ix_{table}_project_id", table, ["project_id"])
    for table in ["job_documents", "records"]:
        op.create_index(f"ix_{table}_job_id", table, ["job_id"])


def downgrade():
    for table in ["records", "job_documents", "extraction_jobs", "extraction_schemas"]:
        op.drop_table(table)
