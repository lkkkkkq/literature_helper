from pydantic import BaseModel

from backend.repositories.health import HealthRepository


class HealthStatus(BaseModel):
    status: str = "ok"
    service: str = "litextract-v2"
    version: str = "0.1.0"
    database: str
    migration: str


class HealthService:
    def __init__(self, repository: HealthRepository):
        self.repository = repository

    def check(self) -> HealthStatus:
        journal, revision = self.repository.probe()
        return HealthStatus(database=journal, migration=revision)
