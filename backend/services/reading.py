import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.core.documents import ParsedContent, ParseRequest
from backend.core.errors import DomainError
from backend.repositories.parsing import ParsingRepository

MAX_SOURCE_BYTES = 200 * 1024 * 1024
logger = logging.getLogger(__name__)


class ReadingService:
    def __init__(self, repository: ParsingRepository, data_dir: Path, parser, recover=True):
        self.repository, self.data_dir, self.parser = repository, data_dir.resolve(), parser
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="document-parser")
        if recover:
            self.repository.recover()

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _read_source(self, asset):
        if asset["status"] == "missing":
            raise DomainError("源文件已缺失，请检查文件并重新扫描。", "conflict")
        root = Path(asset["source_path"])
        path = root / asset["relative_path"]
        try:
            current = path
            while current != root:
                if current.is_symlink() or current.is_junction():
                    raise DomainError("源文件路径已变成链接，请重新扫描。", "conflict")
                if current.parent == current:
                    raise DomainError("文件不在当前项目目录内。")
                current = current.parent
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root.resolve(strict=True)) or resolved != Path(
                asset["absolute_path"]
            ):
                raise DomainError("源文件路径已变化，请重新扫描。", "conflict")
            before = resolved.stat()
            if before.st_size > MAX_SOURCE_BYTES:
                raise DomainError("当前单文件阅读上限为 200 MB，请拆分文档后导入。")
            with resolved.open("rb") as stream:
                data = stream.read(MAX_SOURCE_BYTES + 1)
            after = resolved.stat()
            if len(data) > MAX_SOURCE_BYTES:
                raise DomainError("文件超过 200 MB 的阅读上限。")
            if (before.st_size, before.st_mtime_ns) != (
                after.st_size,
                after.st_mtime_ns,
            ) or hashlib.sha256(data).hexdigest() != asset["sha256"]:
                raise DomainError("源文件内容已经变化，请先重新扫描并确认索引。", "conflict")
            return data
        except OSError as error:
            raise DomainError("无法读取源文件，请检查路径、权限和文件是否仍存在。") from error

    def source(self, project_id, asset_id):
        asset = self.repository.asset(project_id, asset_id)
        if asset["kind"] != "pdf":
            raise DomainError("原文阅读器仅提供 PDF 文件。")
        return self._read_source(asset)

    def status(self, project_id, asset_id):
        state = self.repository.status(project_id, asset_id)
        return {key: value for key, value in state.items() if key != "result_path"}

    def start(self, project_id, asset_id, options: ParseRequest):
        asset = self.repository.asset(project_id, asset_id)
        if asset["kind"] not in {"pdf", "csv", "xlsx", "docx"}:
            raise DomainError("当前解析支持 PDF、CSV、XLSX、DOCX；其他格式请先转换。")
        self._read_source(asset)
        run, claimed = self.repository.claim(asset, self.parser.version, options.ocr, options.force)
        if claimed:
            self.executor.submit(self._parse, run, asset)
        return self.status(project_id, asset_id)

    def _parse(self, run, asset):
        artifact = None
        try:
            if not self.repository.mark_running(run["run_id"]):
                return
            data = self._read_source(asset)
            content = self.parser.parse(data, asset, run["ocr"])
            self._read_source(asset)
            relative = (
                Path("projects")
                / asset["project_id"]
                / "parsed"
                / asset["id"]
                / f"{run['run_id']}.json"
            )
            artifact = self.data_dir / relative
            artifact.parent.mkdir(parents=True, exist_ok=True)
            temporary = artifact.with_suffix(".tmp")
            temporary.write_text(content.model_dump_json(), encoding="utf-8")
            temporary.replace(artifact)
            if not self.repository.finish(run, path=relative.as_posix()):
                artifact.unlink(missing_ok=True)
        except Exception as error:
            if artifact:
                artifact.unlink(missing_ok=True)
            message = (
                str(error)
                if isinstance(error, DomainError)
                else (
                    "解析失败。请检查文件是否损坏/加密，以及解析模型是否已下载；可重试。"
                    f"（{type(error).__name__}）"
                )
            )
            logger.warning("Document parsing failed: %s", type(error).__name__)
            self.repository.finish(run, error=message)

    def content(self, project_id, asset_id):
        state = self.repository.status(project_id, asset_id)
        if state["status"] != "ready" or not state.get("result_path"):
            raise DomainError("当前文件没有可用的解析内容，请完成解析后再查看。", "conflict")
        self._read_source(self.repository.asset(project_id, asset_id))
        path = (self.data_dir / state["result_path"]).resolve()
        if not path.is_relative_to(self.data_dir):
            raise DomainError("解析缓存路径无效，请重新解析。")
        try:
            content = ParsedContent.model_validate_json(path.read_text(encoding="utf-8"))
            if content.asset_id != asset_id or content.source_sha256 != state["source_sha256"]:
                raise ValueError("Cache does not match source")
            return content
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise DomainError("解析缓存不可用，请点击重新解析。") from error
