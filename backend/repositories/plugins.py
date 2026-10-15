from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models.plugins import ProjectPlugin
from backend.db.models.workspace import Project
from backend.repositories.workspace import as_dict, require


class PluginRepository:
    def __init__(self, engine):
        self.engine = engine

    def list(self, project_id):
        with Session(self.engine) as session:
            require(session, Project, project_id)
            return [
                as_dict(row)
                for row in session.scalars(
                    select(ProjectPlugin).where(ProjectPlugin.project_id == project_id)
                )
            ]

    def set(self, project_id, plugin_id, version, enabled):
        with Session(self.engine) as session, session.begin():
            require(session, Project, project_id)
            row = session.get(ProjectPlugin, (project_id, plugin_id))
            if row is None:
                row = ProjectPlugin(project_id=project_id, plugin_id=plugin_id)
                session.add(row)
            row.version, row.enabled = version, enabled
