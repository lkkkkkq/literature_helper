"""Persist parser state and versioned content artifact pointers."""

import sqlalchemy as sa
from alembic import op

revision = "0003_parsed_assets"
down_revision = "0002_workspace"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "parsed_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.String(36),
            sa.ForeignKey("document_assets.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_sha256", sa.String(), nullable=False),
        sa.Column("parser_version", sa.String(), nullable=False),
        sa.Column("ocr", sa.Boolean(), nullable=False),
        sa.Column("result_path", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("started_at", sa.String(), nullable=False),
        sa.Column("finished_at", sa.String(), nullable=True),
    )
    op.create_index("ix_parsed_assets_project_id", "parsed_assets", ["project_id"])


def downgrade():
    op.drop_table("parsed_assets")
