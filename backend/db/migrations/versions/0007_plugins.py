"""Host-owned plugin settings. Plugins never run migrations."""

import sqlalchemy as sa
from alembic import op

revision = "0007_plugins"
down_revision = "0006_reviews"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "project_plugins",
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("plugin_id", sa.String(), primary_key=True),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )


def downgrade():
    op.drop_table("project_plugins")
