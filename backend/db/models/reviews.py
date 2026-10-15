from sqlalchemy import JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base
from backend.db.models.workspace import new_id, now


class ReviewRevision(Base):
    __tablename__ = "review_revisions"
    __table_args__ = (UniqueConstraint("job_id", "version"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    job_id: Mapped[str] = mapped_column(ForeignKey("extraction_jobs.id", ondelete="CASCADE"))
    version: Mapped[int]
    record_id: Mapped[str]
    field_key: Mapped[str]
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)
