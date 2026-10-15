import sqlite3

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from backend.db.database import create_database
from backend.db.models import (
    Base,
    workspace,  # noqa: F401
)


def test_existing_stage_zero_database_upgrades_without_schema_drift(tmp_path):
    with sqlite3.connect(tmp_path / "workspace.db") as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        connection.execute("INSERT INTO alembic_version VALUES ('0001_baseline')")
    engine = create_database(tmp_path)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0007_plugins"
            )
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    finally:
        engine.dispose()
