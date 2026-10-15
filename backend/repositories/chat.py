from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.core.errors import DomainError
from backend.db.models.chat import ChatRun, ModelProfile
from backend.db.models.workspace import ChatSession, Project, now
from backend.repositories.workspace import as_dict, require


class ChatRepository:
    def __init__(self, engine):
        self.engine = engine

    def recover(self):
        with Session(self.engine) as session, session.begin():
            session.execute(
                update(ChatRun)
                .where(ChatRun.status == "running")
                .values(status="failed", error="上次回答被中断，请重新提问。")
            )

    def profile(self, project_id):
        with Session(self.engine) as session:
            require(session, Project, project_id)
            row = session.scalar(select(ModelProfile).where(ModelProfile.project_id == project_id))
            return as_dict(row) if row else None

    def save_profile(self, project_id, profile):
        with Session(self.engine) as session, session.begin():
            require(session, Project, project_id)
            row = session.scalar(select(ModelProfile).where(ModelProfile.project_id == project_id))
            if row is None:
                row = ModelProfile(project_id=project_id)
                session.add(row)
            row.base_url, row.model = profile.base_url, profile.model
            session.flush()
            return as_dict(row)

    def history(self, project_id, session_id):
        with Session(self.engine) as session:
            require(session, ChatSession, session_id, project_id)
            return [
                as_dict(row)
                for row in session.scalars(
                    select(ChatRun)
                    .where(ChatRun.project_id == project_id, ChatRun.session_id == session_id)
                    .order_by(ChatRun.created_at, ChatRun.id)
                )
            ]

    def begin(self, project_id, session_id, question):
        with Session(self.engine) as session, session.begin():
            updated = session.execute(
                update(ChatSession)
                .where(ChatSession.id == session_id, ChatSession.project_id == project_id)
                .values(updated_at=now())
            )
            if updated.rowcount != 1:
                raise DomainError("会话不存在或不属于当前项目。", "not_found")
            old = session.scalar(
                select(ChatRun).where(
                    ChatRun.project_id == project_id, ChatRun.request_id == str(question.request_id)
                )
            )
            if old:
                if old.session_id != session_id or old.question != question.question:
                    raise DomainError("请求标识已被其他问题使用。", "conflict")
                return as_dict(old), False
            active = session.scalar(
                select(ChatRun).where(
                    ChatRun.project_id == project_id,
                    ChatRun.session_id == session_id,
                    ChatRun.status == "running",
                )
            )
            if active:
                raise DomainError("此会话仍在生成回答，请稍后再试。", "conflict")
            row = ChatRun(
                project_id=project_id,
                session_id=session_id,
                request_id=str(question.request_id),
                question=question.question,
                status="running",
            )
            session.add(row)
            session.flush()
            return as_dict(row), True

    def finish(self, run_id, answer=None, error=None):
        with Session(self.engine) as session, session.begin():
            row = session.get(ChatRun, run_id)
            if not row:
                raise DomainError("会话已删除。", "not_found")
            row.answer, row.error, row.status = answer, error, "failed" if error else "complete"
            session.flush()
            return as_dict(row)
