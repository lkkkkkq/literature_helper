from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base
from backend.db.models.workspace import new_id, now


class ParsedAsset(Base):
    __tablename__ = "parsed_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("document_assets.id", ondelete="CASCADE"), unique=True
    )
    run_id: Mapped[str]
    status: Mapped[str]
    source_sha256: Mapped[str]
    parser_version: Mapped[str]
    ocr: Mapped[bool]
    result_path: Mapped[str | None]
    error: Mapped[str | None]
    started_at: Mapped[str] = mapped_column(default=now)
    finished_at: Mapped[str | None]
