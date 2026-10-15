from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.core.errors import DomainError
from backend.core.schemas import GroupConfirm, ScanSnapshot
from backend.db.models.workspace import (
    Asset,
    ChatSession,
    Document,
    Message,
    Project,
    ScanDraft,
    now,
)


def as_dict(model) -> dict:
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}


def require(session: Session, model, key: str, project_id: str | None = None):
    entity = session.get(model, key)
    if entity is None or (project_id is not None and entity.project_id != project_id):
        raise DomainError("记录不存在或不属于当前项目。", "not_found")
    return entity


class WorkspaceRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def list_projects(self):
        with Session(self.engine) as session:
            return [
                as_dict(row)
                for row in session.scalars(select(Project).order_by(Project.created_at))
            ]

    def get_project(self, project_id):
        with Session(self.engine) as session:
            return as_dict(require(session, Project, project_id))

    def create_project(self, name, path):
        with Session(self.engine) as session, session.begin():
            project = Project(name=name, source_path=path)
            session.add(project)
            session.flush()
            return as_dict(project)

    def rename_project(self, project_id, name):
        with Session(self.engine) as session, session.begin():
            project = require(session, Project, project_id)
            project.name = name
            project.updated_at = now()
            session.flush()
            return as_dict(project)

    def delete_project(self, project_id):
        with Session(self.engine) as session, session.begin():
            session.delete(require(session, Project, project_id))

    def list_documents(self, project_id):
        with Session(self.engine) as session:
            require(session, Project, project_id)
            documents = session.scalars(
                select(Document)
                .where(Document.project_id == project_id)
                .order_by(Document.created_at)
            ).all()
            assets = session.scalars(
                select(Asset).where(Asset.project_id == project_id).order_by(Asset.relative_path)
            ).all()
            by_document: dict[str, list[dict]] = {}
            for asset in assets:
                by_document.setdefault(asset.document_id, []).append(as_dict(asset))
            return [{**as_dict(row), "assets": by_document.get(row.id, [])} for row in documents]

    def get_document(self, project_id, document_id):
        with Session(self.engine) as session:
            document = require(session, Document, document_id, project_id)
            assets = session.scalars(
                select(Asset)
                .where(Asset.project_id == project_id, Asset.document_id == document_id)
                .order_by(Asset.relative_path)
            )
            return {**as_dict(document), "assets": [as_dict(asset) for asset in assets]}

    def list_sessions(self, project_id):
        with Session(self.engine) as session:
            require(session, Project, project_id)
            return [
                as_dict(row)
                for row in session.scalars(
                    select(ChatSession)
                    .where(ChatSession.project_id == project_id)
                    .order_by(ChatSession.created_at)
                )
            ]

    def create_session(self, project_id, name):
        with Session(self.engine) as session, session.begin():
            require(session, Project, project_id)
            row = ChatSession(project_id=project_id, name=name)
            session.add(row)
            session.flush()
            return as_dict(row)

    def rename_session(self, project_id, session_id, name):
        with Session(self.engine) as session, session.begin():
            row = require(session, ChatSession, session_id, project_id)
            row.name, row.updated_at = name, now()
            session.flush()
            return as_dict(row)

    def delete_session(self, project_id, session_id):
        with Session(self.engine) as session, session.begin():
            session.delete(require(session, ChatSession, session_id, project_id))

    def messages(self, project_id, session_id):
        with Session(self.engine) as session:
            require(session, ChatSession, session_id, project_id)
            return [
                as_dict(row)
                for row in session.scalars(
                    select(Message)
                    .where(Message.project_id == project_id, Message.session_id == session_id)
                    .order_by(Message.created_at, Message.id)
                )
            ]

    def add_message(self, project_id, session_id, content):
        with Session(self.engine) as session, session.begin():
            conversation = require(session, ChatSession, session_id, project_id)
            row = Message(project_id=project_id, session_id=session_id, content=content)
            conversation.updated_at = now()
            session.add(row)
            session.flush()
            return as_dict(row)

    def save_draft(self, project_id, revision, snapshot: ScanSnapshot):
        with Session(self.engine) as session, session.begin():
            # Acquire the write lock before reading to serialize concurrent scans/deletions.
            updated = session.execute(
                update(Project)
                .where(Project.id == project_id, Project.revision == revision)
                .values(updated_at=now())
            )
            if updated.rowcount != 1:
                raise DomainError("项目在扫描期间发生变化，请重新扫描。", "conflict")
            session.execute(delete(ScanDraft).where(ScanDraft.project_id == project_id))
            draft = ScanDraft(
                project_id=project_id, base_revision=revision, snapshot=snapshot.model_dump()
            )
            session.add(draft)
            session.flush()
            return as_dict(draft)

    def get_draft(self, project_id):
        with Session(self.engine) as session:
            require(session, Project, project_id)
            row = session.scalar(select(ScanDraft).where(ScanDraft.project_id == project_id))
            return as_dict(row) if row else None

    def apply_scan(self, project_id, draft_id, revision, groups: list[GroupConfirm], snapshot):
        with Session(self.engine) as session, session.begin():
            updated = session.execute(
                update(Project)
                .where(Project.id == project_id, Project.revision == revision)
                .values(revision=revision + 1, scanned_at=now(), updated_at=now())
            )
            if updated.rowcount != 1:
                raise DomainError("索引已发生变化，请重新扫描。", "conflict")
            require(session, ScanDraft, draft_id, project_id)
            documents = list(
                session.scalars(select(Document).where(Document.project_id == project_id))
            )
            assets = list(session.scalars(select(Asset).where(Asset.project_id == project_id)))
            by_path = {asset.relative_path: asset for asset in assets}
            by_main = {doc.main_path: doc for doc in documents if doc.main_path}
            by_id = {doc.id: doc for doc in documents}
            used = set()
            for document in documents:
                document.status = "missing"
            for asset in assets:
                asset.status = "missing"
            snapshots = {asset.relative_path: asset for asset in snapshot.assets}
            for group in groups:
                document = by_main.get(group.main_path)
                # Preserve standalone attachment groups by their prior asset ownership.
                if document is None and group.main_path is None:
                    prior = {by_path[p].document_id for p in group.asset_paths if p in by_path}
                    if len(prior) == 1:
                        document = by_id.get(next(iter(prior)))
                if document is None or document.id in used:
                    document = Document(
                        project_id=project_id, title=group.title, main_path=group.main_path
                    )
                    session.add(document)
                    session.flush()
                used.add(document.id)
                document.title, document.main_path, document.status = (
                    group.title,
                    group.main_path,
                    "active",
                )
                for path in group.asset_paths:
                    snap = snapshots[path]
                    asset = by_path.get(path)
                    status = "changed" if asset and asset.sha256 != snap.sha256 else "active"
                    if asset is None:
                        asset = Asset(project_id=project_id, document_id=document.id)
                        session.add(asset)
                    for key, value in snap.model_dump().items():
                        setattr(asset, key, value)
                    asset.document_id = document.id
                    asset.role = "main" if path == group.main_path else "supplement"
                    asset.status = status
            session.execute(delete(ScanDraft).where(ScanDraft.id == draft_id))
        return self.list_documents(project_id)
