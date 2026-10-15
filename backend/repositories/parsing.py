from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.core.errors import DomainError
from backend.db.models.parsing import ParsedAsset
from backend.db.models.workspace import Asset, Project, new_id, now
from backend.repositories.workspace import as_dict, require


class ParsingRepository:
    def __init__(self, engine):
        self.engine = engine

    def recover(self):
        with Session(self.engine) as session, session.begin():
            session.execute(
                update(ParsedAsset)
                .where(ParsedAsset.status.in_(["queued", "running"]))
                .values(
                    status="interrupted",
                    error="上次解析被中断，请点击重新解析。",
                    finished_at=now(),
                )
            )

    def asset(self, project_id, asset_id):
        with Session(self.engine) as session:
            asset = require(session, Asset, asset_id, project_id)
            project = require(session, Project, project_id)
            return {**as_dict(asset), "source_path": project.source_path}

    def status(self, project_id, asset_id):
        with Session(self.engine) as session:
            asset = require(session, Asset, asset_id, project_id)
            row = session.scalar(
                select(ParsedAsset).where(
                    ParsedAsset.asset_id == asset_id, ParsedAsset.project_id == project_id
                )
            )
            if row is None:
                return {"asset_id": asset_id, "status": "unparsed"}
            value = as_dict(row)
            if asset.sha256 != row.source_sha256 or asset.status == "missing":
                value.update(status="stale", error="源文件索引已更新或缺失，请重新解析。")
            return value

    def claim(self, asset, version, ocr, force):
        with Session(self.engine) as session, session.begin():
            updated = session.execute(
                update(Asset)
                .where(
                    Asset.id == asset["id"],
                    Asset.project_id == asset["project_id"],
                    Asset.sha256 == asset["sha256"],
                    Asset.status != "missing",
                )
                .values(status=Asset.status)
            )
            if updated.rowcount != 1:
                raise DomainError("文件索引已变化，请刷新后重试。", "conflict")
            row = session.scalar(select(ParsedAsset).where(ParsedAsset.asset_id == asset["id"]))
            if row and row.status in {"queued", "running"}:
                return as_dict(row), False
            if (
                row
                and not force
                and row.status == "ready"
                and row.source_sha256 == asset["sha256"]
                and row.parser_version == version
                and row.ocr == ocr
            ):
                return as_dict(row), False
            if row is None:
                row = ParsedAsset(project_id=asset["project_id"], asset_id=asset["id"])
                session.add(row)
            row.run_id, row.status, row.source_sha256 = new_id(), "queued", asset["sha256"]
            row.parser_version, row.ocr, row.started_at = version, ocr, now()
            row.result_path = row.error = row.finished_at = None
            session.flush()
            return as_dict(row), True

    def mark_running(self, run_id):
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                update(ParsedAsset)
                .where(ParsedAsset.run_id == run_id, ParsedAsset.status == "queued")
                .values(status="running")
            )
            return result.rowcount == 1

    def finish(self, run, path=None, error=None):
        with Session(self.engine) as session, session.begin():
            asset = session.get(Asset, run["asset_id"])
            if not asset:
                return False
            if asset.sha256 != run["source_sha256"] or asset.status == "missing":
                path, error = None, "解析期间源文件索引发生变化，请重新解析。"
            result = session.execute(
                update(ParsedAsset)
                .where(ParsedAsset.run_id == run["run_id"])
                .values(
                    status="failed" if error else "ready",
                    result_path=path,
                    error=error,
                    finished_at=now(),
                )
            )
            return result.rowcount == 1 and not error
