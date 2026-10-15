from sqlalchemy import JSON, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base
from backend.db.models.workspace import new_id, now


class ExtractionSchema(Base):
    __tablename__ = "extraction_schemas"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "session_id"],
            ["chat_sessions.project_id", "chat_sessions.id"],
            ondelete="CASCADE",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str]
    version: Mapped[int]
    status: Mapped[str]
    goal: Mapped[str]
    plan: Mapped[dict] = mapped_column(JSON)
    document_ids: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"
    __table_args__ = (
        UniqueConstraint("project_id", "request_id"),
        ForeignKeyConstraint(
            ["project_id", "session_id"],
            ["chat_sessions.project_id", "chat_sessions.id"],
            ondelete="CASCADE",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str]
    schema_id: Mapped[str] = mapped_column(ForeignKey("extraction_schemas.id", ondelete="CASCADE"))
    request_id: Mapped[str]
    status: Mapped[str]
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(default=now)
    error: Mapped[str | None]


class JobDocument(Base):
    __tablename__ = "job_documents"
    __table_args__ = (UniqueConstraint("job_id", "document_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_jobs.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    status: Mapped[str]
    fingerprints: Mapped[dict] = mapped_column(JSON)
    error: Mapped[str | None]
    warnings: Mapped[list] = mapped_column(JSON, default=list)


class Record(Base):
    __tablename__ = "records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_jobs.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    values_json: Mapped[dict] = mapped_column(JSON)
    evidence_json: Mapped[list] = mapped_column(JSON)
    risks: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)
