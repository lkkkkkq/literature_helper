from sqlalchemy import text
from sqlalchemy.engine import Engine


class HealthRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def probe(self) -> tuple[str, str]:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            journal = connection.execute(text("PRAGMA journal_mode")).scalar_one()
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        return journal, revision
