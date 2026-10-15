from copy import deepcopy

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.core.chat import Evidence
from backend.core.errors import DomainError
from backend.core.extraction import ExtractionPlan
from backend.db.models.jobs import ExtractionJob, ExtractionSchema, Record
from backend.db.models.reviews import ReviewRevision
from backend.extraction.metadata import metadata_kind
from backend.extraction.validation import validate_records
from backend.plugins.manager import PluginCatalog
from backend.repositories.workspace import as_dict, require


class ReviewRepository:
    def __init__(self, engine):
        self.engine = engine

    def _snapshot(self, session, project_id, job_id, version):
        job = require(session, ExtractionJob, job_id, project_id)
        schema = require(session, ExtractionSchema, job.schema_id, project_id)
        rows = [
            as_dict(row)
            for row in session.scalars(
                select(Record)
                .where(Record.project_id == project_id, Record.job_id == job_id)
                .order_by(Record.created_at, Record.id)
            )
        ]
        history = [
            as_dict(row)
            for row in session.scalars(
                select(ReviewRevision)
                .where(ReviewRevision.project_id == project_id, ReviewRevision.job_id == job_id)
                .order_by(ReviewRevision.version)
            )
        ]
        latest = len(history)
        if version == "latest":
            selected = latest
        elif version == "automatic":
            selected = 0
        else:
            try:
                selected = int(version)
            except ValueError as error:
                raise DomainError("无效的复核版本。") from error
            if not 0 <= selected <= latest:
                raise DomainError("复核版本不存在。", "not_found")
        by_id = {row["id"]: row for row in rows}
        for change in history[:selected]:
            row = by_id.get(change["record_id"])
            if row:
                row["values_json"][change["field_key"]] = deepcopy(change["after"])
                row["risks"] = list(
                    dict.fromkeys(row["risks"] + ["包含人工修订，请结合修订原因复核"])
                )
        if selected:
            plan = ExtractionPlan.model_validate(schema.plan)
            for row in rows:
                checked, _ = validate_records(
                    {"records": [{"fields": row["values_json"], "risks": []}]},
                    plan,
                    [Evidence.model_validate(item) for item in row["evidence_json"]],
                    document_id=row["document_id"],
                )
                row["risks"] = list(dict.fromkeys(row["risks"] + checked[0]["risks"]))
                row["values_json"] = checked[0]["values_json"]
        return dict(
            records=rows,
            history=history,
            version=selected,
            latest_version=latest,
            schema=as_dict(schema),
            job=as_dict(job),
        )

    def snapshot(self, project_id, job_id, version="latest"):
        with Session(self.engine) as session:
            return self._snapshot(session, project_id, job_id, version)

    def append(self, project_id, job_id, body):
        with Session(self.engine) as session, session.begin():
            session.execute(
                update(ExtractionJob)
                .where(ExtractionJob.id == job_id, ExtractionJob.project_id == project_id)
                .values(status=ExtractionJob.status)
            )
            snapshot = self._snapshot(session, project_id, job_id, "latest")
            if snapshot["job"]["status"] in {"pending", "running"}:
                raise DomainError("请等待任务停止后再复核。", "conflict")
            if snapshot["version"] != body.base_version:
                raise DomainError("复核版本已更新，请刷新后重试。", "conflict")
            row = next((row for row in snapshot["records"] if row["id"] == body.record_id), None)
            if row is None or body.field_key not in row["values_json"]:
                raise DomainError("记录或字段不存在。", "not_found")
            plan = ExtractionPlan.model_validate(snapshot["schema"]["plan"])
            field = next(item for item in plan.fields if item.key == body.field_key)
            if metadata_kind(field):
                raise DomainError(
                    "系统文献索引、缺失原因、风险和证据列由系统维护，请修改对应研究字段。"
                )
            before = deepcopy(row["values_json"][body.field_key])
            row["values_json"][body.field_key] = body.after.model_dump()
            validate_records(
                {"records": [{"fields": row["values_json"], "risks": []}]},
                plan,
                [Evidence.model_validate(item) for item in row["evidence_json"]],
                document_id=row["document_id"],
            )
            PluginCatalog().apply([row], snapshot["schema"]["plan"].get("plugins", []))
            revision = ReviewRevision(
                project_id=project_id,
                job_id=job_id,
                version=snapshot["version"] + 1,
                record_id=body.record_id,
                field_key=body.field_key,
                before=before,
                after=row["values_json"][body.field_key],
                reason=body.reason.strip(),
            )
            if not revision.reason:
                raise DomainError("请填写修订原因。")
            session.add(revision)
            session.flush()
            return as_dict(revision)
