from sqlalchemy import JSON, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base
from backend.db.models.workspace import new_id, now


class ModelProfile(Base):
    __tablename__ = "model_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    base_url: Mapped[str]
    model: Mapped[str]


class ChatRun(Base):
    __tablename__ = "chat_runs"
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
    request_id: Mapped[str]
    status: Mapped[str]
    question: Mapped[str]
    answer: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)
