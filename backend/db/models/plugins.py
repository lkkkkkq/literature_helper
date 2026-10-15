from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base


class ProjectPlugin(Base):
    __tablename__ = "project_plugins"
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    plugin_id: Mapped[str] = mapped_column(primary_key=True)
    version: Mapped[str]
    enabled: Mapped[bool]
