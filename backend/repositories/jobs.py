from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from backend.core.errors import DomainError
from backend.db.models.jobs import ExtractionJob, ExtractionSchema, JobDocument, Record
from backend.db.models.workspace import ChatSession, now
from backend.repositories.workspace import as_dict, require


class JobRepository:
    def __init__(self, engine):
        self.engine = engine

    def recover(self):
        with Session(self.engine) as session, session.begin():
            session.execute(
                update(ExtractionJob)
                .where(ExtractionJob.status.in_(["pending", "running"]))
                .values(status="interrupted", error="上次任务被中断，可恢复未完成文献。")
            )
            session.execute(
                update(JobDocument)
                .where(JobDocument.status == "running")
                .values(status="interrupted")
            )

    def plans(self, project_id, session_id):
        with Session(self.engine) as session:
            require(session, ChatSession, session_id, project_id)
            return [
                as_dict(row)
                for row in session.scalars(
                    select(ExtractionSchema)
                    .where(
                        ExtractionSchema.project_id == project_id,
                        ExtractionSchema.session_id == session_id,
                    )
                    .order_by(ExtractionSchema.version)
                )
            ]

    def draft(self, project_id, session_id, goal, plan, document_ids):
        with Session(self.engine) as session, session.begin():
            self._lock_session(session, project_id, session_id)
            version = (
                session.scalar(
                    select(func.max(ExtractionSchema.version)).where(
                        ExtractionSchema.project_id == project_id,
                        ExtractionSchema.session_id == session_id,
                    )
                )
                or 0
            )
            row = ExtractionSchema(
                project_id=project_id,
                session_id=session_id,
                goal=goal,
                plan=plan.model_dump(),
                document_ids=document_ids,
                version=version + 1,
                status="draft",
            )
            session.add(row)
            session.flush()
            return as_dict(row)

    def _lock_session(self, session, project_id, session_id):
        updated = session.execute(
            update(ChatSession)
            .where(ChatSession.project_id == project_id, ChatSession.id == session_id)
            .values(updated_at=now())
        )
        if updated.rowcount != 1:
            raise DomainError("会话不存在或不属于此项目。", "not_found")

    def confirm(self, project_id, session_id, body, fingerprints):
        with Session(self.engine) as session, session.begin():
            self._lock_session(session, project_id, session_id)
            old = session.scalar(
                select(ExtractionJob).where(
                    ExtractionJob.project_id == project_id,
                    ExtractionJob.request_id == str(body.request_id),
                )
            )
            if old:
                if old.session_id != session_id:
                    raise DomainError("请求标识已被使用。", "conflict")
                return as_dict(old)
            source = require(session, ExtractionSchema, str(body.schema_id), project_id)
            if source.session_id != session_id:
                raise DomainError("方案不属于当前会话。", "not_found")
            version = (
                session.scalar(
                    select(func.max(ExtractionSchema.version)).where(
                        ExtractionSchema.project_id == project_id,
                        ExtractionSchema.session_id == session_id,
                    )
                )
                or 0
            )
            schema = ExtractionSchema(
                project_id=project_id,
                session_id=session_id,
                goal=source.goal,
                plan=body.plan.model_dump(),
                document_ids=source.document_ids,
                version=version + 1,
                status="confirmed",
            )
            session.add(schema)
            session.flush()
            job = ExtractionJob(
                project_id=project_id,
                session_id=session_id,
                schema_id=schema.id,
                request_id=str(body.request_id),
                status="pending",
            )
            session.add(job)
            session.flush()
            for document_id in schema.document_ids:
                session.add(
                    JobDocument(
                        project_id=project_id,
                        job_id=job.id,
                        document_id=document_id,
                        status="pending",
                        fingerprints=fingerprints[document_id],
                    )
                )
            session.flush()
            return as_dict(job)

    def list(self, project_id, session_id):
        with Session(self.engine) as session:
            require(session, ChatSession, session_id, project_id)
            return [
                as_dict(row)
                for row in session.scalars(
                    select(ExtractionJob)
                    .where(
                        ExtractionJob.project_id == project_id,
                        ExtractionJob.session_id == session_id,
                    )
                    .order_by(ExtractionJob.created_at.desc())
                )
            ]

    def get(self, project_id, job_id):
        with Session(self.engine) as session:
            job = require(session, ExtractionJob, job_id, project_id)
            documents = [
                as_dict(row)
                for row in session.scalars(
                    select(JobDocument).where(JobDocument.job_id == job_id).order_by(JobDocument.id)
                )
            ]
            count = session.scalar(
                select(func.count()).select_from(Record).where(Record.job_id == job_id)
            )
            return {
                **as_dict(job),
                "documents": documents,
                "schema": as_dict(require(session, ExtractionSchema, job.schema_id, project_id)),
                "record_count": count,
            }

    def claim(self, project_id, job_id):
        with Session(self.engine) as session, session.begin():
            changed = session.execute(
                update(ExtractionJob)
                .where(
                    ExtractionJob.id == job_id,
                    ExtractionJob.project_id == project_id,
                    ExtractionJob.status == "pending",
                    ExtractionJob.cancel_requested.is_(False),
                )
                .values(status="running", error=None)
            )
            return changed.rowcount == 1

    def begin_document(self, project_id, job_id, document_id):
        with Session(self.engine) as session, session.begin():
            job = require(session, ExtractionJob, job_id, project_id)
            if job.cancel_requested or job.status != "running":
                return False
            changed = session.execute(
                update(JobDocument)
                .where(
                    JobDocument.job_id == job_id,
                    JobDocument.document_id == document_id,
                    JobDocument.status == "pending",
                )
                .values(status="running", error=None)
            )
            return changed.rowcount == 1

    def finish_document(self, project_id, job_id, document_id, records=(), warnings=(), error=None):
        with Session(self.engine) as session, session.begin():
            # Acquire SQLite's writer lock before checking cancellation.
            changed = session.execute(
                update(ExtractionJob)
                .where(
                    ExtractionJob.id == job_id,
                    ExtractionJob.project_id == project_id,
                    ExtractionJob.status == "running",
                    ExtractionJob.cancel_requested.is_(False),
                )
                .values(status="running")
            )
            if changed.rowcount != 1:
                return False
            row = session.scalar(
                select(JobDocument).where(
                    JobDocument.job_id == job_id, JobDocument.document_id == document_id
                )
            )
            if not row:
                return False
            session.execute(
                delete(Record).where(Record.job_id == job_id, Record.document_id == document_id)
            )
            for values in records:
                session.add(
                    Record(project_id=project_id, job_id=job_id, document_id=document_id, **values)
                )
            row.status, row.error, row.warnings = (
                "failed" if error else "complete",
                error,
                list(warnings),
            )
            return True

    def finish(self, project_id, job_id):
        with Session(self.engine) as session, session.begin():
            job = require(session, ExtractionJob, job_id, project_id)
            if job.status != "running":
                return
            states = list(
                session.scalars(select(JobDocument.status).where(JobDocument.job_id == job_id))
            )
            job.status = (
                "completed"
                if all(state == "complete" for state in states)
                else "partial"
                if "complete" in states
                else "failed"
            )

    def cancel(self, project_id, job_id, interrupted=False):
        with Session(self.engine) as session, session.begin():
            job = require(session, ExtractionJob, job_id, project_id)
            if job.status not in {"pending", "running"}:
                return
            job.cancel_requested, job.status = True, "interrupted" if interrupted else "cancelled"
            session.execute(
                update(JobDocument)
                .where(JobDocument.job_id == job_id, JobDocument.status.in_(["pending", "running"]))
                .values(status=job.status)
            )

    def resume(self, project_id, job_id):
        with Session(self.engine) as session, session.begin():
            job = require(session, ExtractionJob, job_id, project_id)
            if job.status in {"pending", "running", "completed"}:
                raise DomainError("当前任务不能恢复。", "conflict")
            job.status, job.cancel_requested, job.error = "pending", False, None
            session.execute(
                update(JobDocument)
                .where(JobDocument.job_id == job_id, JobDocument.status != "complete")
                .values(status="pending", error=None)
            )

    def records(self, project_id, job_id):
        with Session(self.engine) as session:
            require(session, ExtractionJob, job_id, project_id)
            return [
                as_dict(row)
                for row in session.scalars(
                    select(Record)
                    .where(Record.project_id == project_id, Record.job_id == job_id)
                    .order_by(Record.created_at, Record.id)
                )
            ]
