"""New parser artifacts live beside, never replace, legacy evidence caches."""

import base64
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import ValidationError

from backend.core.errors import DomainError
from backend.parsing_next.bundle import (
    fulltext_batches,
    load_bundle,
    safe_child,
    valid_id,
    write_json,
)
from backend.parsing_next.charts import ChartInput, digitize
from backend.parsing_next.native import parse_native
from backend.parsing_next.runner import run_parser


class FullDocumentService:
    def __init__(self, reading, data_dir):
        self.reading = reading
        self.root = Path(data_dir) / "parser-next"
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="full-parser")
        self.lock = threading.RLock()
        self.tasks = {}

    def folder(self, project, asset):
        self.reading.repository.asset(project, asset)
        return self.root / valid_id(project) / valid_id(asset)

    def status(self, project, asset):
        folder = self.folder(project, asset)
        with self.lock:
            active = (
                json.loads((folder / "active.json").read_text("utf-8"))
                if (folder / "active.json").exists()
                else None
            )
            task = self.tasks.get((project, asset))
            state = {k: v for k, v in task.items() if k != "cancel"} if task else {"status": "idle"}
            if not task and (folder / "task.json").exists():
                state = json.loads((folder / "task.json").read_text("utf-8"))
                if state["status"] in {"queued", "running"}:
                    state.update(status="interrupted", error="上次解析中断；上一可用版本保留。")
            return {**state, "active": active}

    def start(self, project, asset, pages="all"):
        source = self.reading.repository.asset(project, asset)
        self.reading._read_source(source)
        if source["kind"] not in {"pdf", "docx", "tex", "md", "csv", "xlsx"}:
            raise DomainError("新版支持 PDF、DOCX、LaTeX、Markdown、CSV 和 XLSX。")
        folder = self.folder(project, asset)
        if pages != "all":
            import re

            if source["kind"] != "pdf" or not re.fullmatch(
                r"[1-9][0-9]*(?:-[1-9][0-9]*)?(?:,[1-9][0-9]*(?:-[1-9][0-9]*)?)*", pages
            ):
                raise DomainError("逐页重做仅支持 PDF，页码格式如 3 或 3-5,8。")
            if not (folder / "active.json").is_file():
                raise DomainError("请先完成整篇解析，再单独重做页面。")
        with self.lock:
            previous = self.tasks.get((project, asset))
            if previous and previous["status"] in {"queued", "running"}:
                return self.status(project, asset)
            task = {
                "version": str(uuid.uuid4()),
                "status": "queued",
                "cancel": threading.Event(),
                "pages": pages,
            }
            self.tasks[project, asset] = task
            folder.mkdir(parents=True, exist_ok=True)
            self._record(folder, task)
            self.executor.submit(self._parse, source, folder, task)
        return self.status(project, asset)

    def _record(self, folder, task):
        write_json(folder / "task.json", {k: v for k, v in task.items() if k != "cancel"})

    def _parse(self, asset, folder, task):
        output = folder / task["version"]
        try:
            with self.lock:
                task["status"] = "running"
                self._record(folder, task)
            self.reading._read_source(asset)
            if task["cancel"].is_set():
                raise DomainError("解析已取消。")
            if asset["kind"] == "pdf":
                partial = (
                    output.with_name(output.name + "-pages") if task["pages"] != "all" else output
                )
                run_parser(
                    asset["absolute_path"],
                    partial,
                    cancel=task["cancel"],
                    version=task["version"],
                    pages=task["pages"],
                )
                if partial != output:
                    from backend.parsing_next.repair import merge_pages

                    active = json.loads((folder / "active.json").read_text("utf-8"))
                    merge_pages(
                        folder / active["version"],
                        partial,
                        output,
                        Path(asset["absolute_path"]),
                        task["version"],
                    )
            else:
                parse_native(asset["absolute_path"], output, task["version"], task["cancel"])
            self.reading._read_source(asset)
            _, index, report = load_bundle(output)
            if index["source_sha256"] != asset["sha256"]:
                raise DomainError("解析源文件摘要不一致。")
            with self.lock:
                if task["cancel"].is_set():
                    raise DomainError("解析已取消；产物未激活。")
                write_json(
                    folder / "active.json",
                    {
                        "version": task["version"],
                        "source_sha256": asset["sha256"],
                        "status": report["status"],
                    },
                )
                task["status"] = "ready"
        except Exception as error:
            with self.lock:
                task.update(
                    status="cancelled" if task["cancel"].is_set() else "failed", error=str(error)
                )
        finally:
            with self.lock:
                self._record(folder, task)

    def cancel(self, project, asset):
        self.folder(project, asset)
        with self.lock:
            task = self.tasks.get((project, asset))
            if task and task["status"] in {"queued", "running"}:
                task["cancel"].set()
        return self.status(project, asset)

    def version_folder(self, project, asset, version):
        folder = self.folder(project, asset)
        return folder / valid_id(version)

    def content(self, project, asset, version):
        folder = self.version_folder(project, asset, version)
        markdown, index, report = load_bundle(folder)
        corrections = self.corrections(project, asset, version)
        chart_history = self.charts(project, asset, version)
        report["chart_revisions"] = [
            {
                "revision": item["revision"],
                "resource": item["specification"]["resource"],
                "panel": item["specification"]["panel"],
                "series": item["specification"]["series"],
                "confirmed": item["specification"]["confirmed"],
            }
            for item in chart_history
        ]
        return {
            "markdown": markdown,
            "sources": index,
            "report": report,
            "corrections": corrections,
            "blocks": [
                {**block, "markdown": markdown[block["start"] : block["end"]]}
                for block in index["blocks"]
            ],
        }

    def resource(self, project, asset, version, name):
        folder = self.version_folder(project, asset, version)
        _, index, _ = load_bundle(folder)
        allowed = {name for block in index["blocks"] for name in block["resources"]}
        if name not in allowed:
            raise DomainError("资源不在来源索引中。")
        path = safe_child(folder, name)
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(path.suffix.lower())
        if not mime:
            if path.suffix.lower() in {".json", ".md", ".txt", ".csv"}:
                try:
                    text = path.read_text(encoding="utf-8-sig")
                except UnicodeDecodeError:
                    from charset_normalizer import from_bytes

                    detected = from_bytes(path.read_bytes()).best()
                    text = str(detected) if detected else "无法可靠解码，请核对原始附件。"
                return {"text": text, "name": name}
            return {"text": "此资源保留为原始文件，请使用对应源文件查看。", "name": name}
        return {
            "data_url": f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode(),
            "name": name,
        }

    def corrections(self, project, asset, version):
        folder = self.version_folder(project, asset, version) / "corrections"
        return [json.loads(path.read_text("utf-8")) for path in sorted(folder.glob("*.json"))]

    def correct(self, project, asset, version, body):
        folder = self.version_folder(project, asset, version)
        _, index, _ = load_bundle(folder)
        if body.get("block_id") not in {block["id"] for block in index["blocks"]}:
            raise DomainError("修正内容不属于此解析版本。")
        if not isinstance(body.get("markdown"), str) or len(body["markdown"]) > 200000:
            raise DomainError("修正内容无效或过长。")
        if not str(body.get("reason", "")).strip():
            raise DomainError("请填写修正原因。")
        with self.lock:
            history = self.corrections(project, asset, version)
            if body.get("base_revision") != len(history):
                raise DomainError("修正记录已变化，请刷新后重试。", "conflict")
            revision = {
                "revision": len(history) + 1,
                "block_id": body["block_id"],
                "markdown": body["markdown"],
                "reason": body["reason"],
            }
            (folder / "corrections").mkdir(exist_ok=True)
            write_json(folder / "corrections" / f"{revision['revision']:06d}.json", revision)
        return revision

    def save_chart(self, project, asset, version, body):
        try:
            specification = ChartInput.model_validate(body)
        except ValidationError as error:
            raise DomainError("图表标定输入无效，请检查坐标、类型和必填字段。") from error
        self.resource(project, asset, version, specification.resource)
        rows = digitize(specification)
        folder = self.version_folder(project, asset, version) / "chart-data"
        with self.lock:
            history = sorted(folder.glob("revision-*.json"))
            if specification.base_revision != len(history):
                raise DomainError("图表记录已变化，请刷新后保存。", "conflict")
            result = {
                "revision": len(history) + 1,
                "version": version,
                "specification": specification.model_dump(),
                "rows": rows,
            }
            write_json(folder / f"revision-{result['revision']:06d}.json", result)
        return result

    def charts(self, project, asset, version):
        folder = self.version_folder(project, asset, version) / "chart-data"
        return [
            json.loads(path.read_text("utf-8")) for path in sorted(folder.glob("revision-*.json"))
        ]

    def fulltext(self, project, asset, version, budget):
        return fulltext_batches(self.version_folder(project, asset, version), budget)

    def prefer_source(self, project, asset, confirmed):
        from backend.repositories.workspace import WorkspaceRepository

        source = self.reading.repository.asset(project, asset)
        if confirmed is False:
            path = self.root / valid_id(project) / "source-preferences.json"
            with self.lock:
                preferences = json.loads(path.read_text("utf-8")) if path.exists() else {}
                preferences.pop(source["document_id"], None)
                path.parent.mkdir(parents=True, exist_ok=True)
                write_json(path, preferences)
            return {"notice": "已恢复按主论文和附件分别提供内容。"}
        if source["kind"] not in {"docx", "tex", "md"} or confirmed is not True:
            raise DomainError("请先人工核对标题、正文和版本，确认此文件与主 PDF 为同一版本。")
        document = WorkspaceRepository(self.reading.repository.engine).get_document(
            project, source["document_id"]
        )
        pdf = next(
            (
                item
                for item in document["assets"]
                if item["role"] == "main" and item["kind"] == "pdf"
            ),
            None,
        )
        if not pdf:
            raise DomainError("当前文献没有可关联的主 PDF；原生文件仍可独立使用。")
        state = self.status(project, asset)
        if not state.get("active"):
            raise DomainError("请先完成此原生文件的新版本解析。")
        path = self.root / valid_id(project) / "source-preferences.json"
        with self.lock:
            preferences = json.loads(path.read_text("utf-8")) if path.exists() else {}
            preferences[source["document_id"]] = {
                "asset_id": asset,
                "source_sha256": source["sha256"],
                "pdf_asset_id": pdf["id"],
                "pdf_sha256": pdf["sha256"],
                "confirmed_same_version": True,
            }
            write_json(path, preferences)
        return {"preferred_asset": asset, "notice": "原生正文优先；PDF 保留核对，未伪造对应页码。"}

    def close(self):
        with self.lock:
            for task in self.tasks.values():
                if task["status"] in {"queued", "running"}:
                    task["cancel"].set()
        self.executor.shutdown(wait=False, cancel_futures=True)
