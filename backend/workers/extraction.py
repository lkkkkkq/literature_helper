"""One isolated process executes a durable SQLite job; credentials are memory-only."""

import os
import time
from pathlib import Path


def run_job(
    data_dir: str, project_id: str, job_id: str, profile: dict, key: str, watch_parent=False
):
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    from backend.parsers.docling_adapter import DoclingAdapter, prepare_native_runtime

    prepare_native_runtime()
    if watch_parent:
        import sys
        import threading

        def monitor_parent():
            sys.stdin.read()
            os._exit(0)

        threading.Thread(target=monitor_parent, daemon=True).start()
    from backend.agent.extract_graph import extract
    from backend.agent.model_adapter import CompatibleModel
    from backend.core.documents import ParseRequest
    from backend.core.errors import DomainError
    from backend.core.extraction import ExtractionPlan
    from backend.db.database import create_database
    from backend.plugins.manager import PluginCatalog
    from backend.repositories.jobs import JobRepository
    from backend.repositories.parsing import ParsingRepository
    from backend.repositories.workspace import WorkspaceRepository
    from backend.services.context import DocumentContext
    from backend.services.reading import ReadingService

    engine = create_database(Path(data_dir))
    repository = JobRepository(engine)
    workspace = WorkspaceRepository(engine)
    model_dir = Path(
        os.environ.get(
            "LITEXTRACT_MODEL_DIR",
            str(Path(__file__).resolve().parents[2] / ".local/docling-models"),
        )
    )
    reading = ReadingService(
        ParsingRepository(engine), Path(data_dir), DoclingAdapter(model_dir), recover=False
    )
    context = DocumentContext(workspace, reading)
    try:
        if not repository.claim(project_id, job_id):
            return
        job = repository.get(project_id, job_id)
        plan = ExtractionPlan.model_validate(job["schema"]["plan"])
        catalog = PluginCatalog()
        for document in job["documents"]:
            document_id = document["document_id"]
            if not repository.begin_document(project_id, job_id, document_id):
                continue
            try:
                current = workspace.get_document(project_id, document_id)
                catalog.resolve(plan.plugins)
                if {asset["id"]: asset["sha256"] for asset in current["assets"]} != document[
                    "fingerprints"
                ]:
                    raise DomainError("文献索引已变化，不能沿用已确认的任务，请新建方案。")
                for asset in current["assets"]:
                    from backend.parsing_next.context import active_sources

                    if active_sources(reading, project_id, document_id, asset) is not None:
                        continue
                    if asset["kind"] not in {"pdf", "csv", "xlsx", "docx"}:
                        continue
                    if reading.status(project_id, asset["id"])["status"] != "ready":
                        reading.start(
                            project_id, asset["id"], ParseRequest(ocr=asset["kind"] == "pdf")
                        )
                        deadline = time.monotonic() + 600
                        while reading.status(project_id, asset["id"])["status"] in {
                            "queued",
                            "running",
                        }:
                            if time.monotonic() > deadline:
                                raise DomainError("文档解析超时，请单独解析后新建任务。")
                            time.sleep(0.2)
                        if reading.status(project_id, asset["id"])["status"] != "ready":
                            raise DomainError(f"附件 {asset['relative_path']} 解析失败。")
                sources, warnings = context.sources(project_id, [document_id])
                if not sources:
                    raise DomainError("此文献没有可提取的原文。")
                batches, batch, length = [], [], 0
                for source in sources:
                    if batch and length + len(source.quote) > 40000:
                        batches.append(batch)
                        batch, length = [], 0
                    batch.append(source)
                    length += len(source.quote)
                if batch:
                    batches.append(batch)
                records = []
                for batch in batches:
                    if repository.get(project_id, job_id)["cancel_requested"]:
                        return
                    rows, notices = extract(CompatibleModel(), profile, key, plan, batch)
                    records.extend(rows)
                    warnings.extend(notices)
                if len(batches) > 1:
                    warnings.append("长文按内容批次提取；跨批次的记录归并与重复需要复核。")
                    for row in records:
                        row["risks"].append("长文分批提取，需检查记录是否重复或拆分")
                for asset in current["assets"]:
                    reading._read_source(reading.repository.asset(project_id, asset["id"]))
                catalog.apply(records, plan.plugins)
                repository.finish_document(project_id, job_id, document_id, records, warnings)
            except Exception as error:
                message = (
                    str(error)
                    if isinstance(error, DomainError)
                    else "此文献提取失败：模型输出或文档处理不符合要求。"
                )
                repository.finish_document(project_id, job_id, document_id, error=message)
        repository.finish(project_id, job_id)
    finally:
        reading.close()
        engine.dispose()


if __name__ == "__main__":
    import json
    import sys

    arguments = json.loads(sys.stdin.readline())
    run_job(**arguments, watch_parent=True)
