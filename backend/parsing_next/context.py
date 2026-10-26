"""Read all current Markdown and reviewed chart data; never rank by a query."""

import hashlib
import json
from pathlib import Path

from backend.core.chat import Evidence
from backend.core.documents import SourceLocation
from backend.core.errors import DomainError
from backend.parsing_next.bundle import load_bundle, safe_child


def active_sources(reading, project_id, document_id, asset):
    root = reading.data_dir / "parser-next" / project_id / asset["id"]
    if not (root / "active.json").is_file():
        return None
    original_asset = reading.repository.asset(project_id, asset["id"])
    reading._read_source(original_asset)
    active = json.loads((root / "active.json").read_text("utf-8"))
    if active["source_sha256"] != asset["sha256"]:
        raise DomainError("新版全文对应的源文件已变化，请重新解析。")
    folder = root / active["version"]
    markdown, index, report = load_bundle(folder)
    for dependency in report.get("dependencies", []):
        original = safe_child(Path(original_asset["absolute_path"]).parent, dependency["file"])
        if (
            not original.is_file()
            or hashlib.sha256(original.read_bytes()).hexdigest() != dependency["sha256"]
        ):
            raise DomainError("原生文档的图片或依赖文件已变化，请重新解析后使用全文。")
    revisions = {}
    for path in sorted((folder / "corrections").glob("*.json")):
        revision = json.loads(path.read_text("utf-8"))
        revisions[revision["block_id"]] = revision
    sources = []
    for block in index["blocks"]:
        correction = revisions.get(block["id"])
        text = correction["markdown"] if correction else markdown[block["start"] : block["end"]]
        for resource in block["resources"]:
            if resource.startswith("chart-data/") and resource.endswith("-native.json"):
                text += "\n原生图表缓存数值（需核对）：\n" + (folder / resource).read_text("utf-8")
        if correction:
            text = f"[人工修正版本 {correction['revision']}，原文需核对]\n" + text
        for start in range(0, len(text), 12000):
            sources.append(
                Evidence(
                    id=f"N{len(sources) + 1}",
                    document_id=document_id,
                    asset_id=asset["id"],
                    filename=asset["relative_path"],
                    source_sha256=asset["sha256"],
                    block_id=block["id"],
                    quote=text[start : start + 12000],
                    locations=[
                        SourceLocation.model_validate(loc)
                        for loc in block["locations"]
                        if loc.get("page")
                    ],
                    kind=block["kind"],
                    parse_version=index["version"],
                    source_position=block["locations"],
                )
            )
    # Only the latest revision of each explicitly identified panel and series is used.
    charts = {}
    for path in sorted((folder / "chart-data").glob("revision-*.json")):
        item = json.loads(path.read_text("utf-8"))
        spec = item["specification"]
        charts[spec["resource"], spec["panel"], spec["series"]] = item
    for item in charts.values():
        if not item["specification"]["confirmed"]:
            continue
        spec = item["specification"]
        text = json.dumps(
            {
                "method": spec["kind"],
                "units": [spec["x_unit"], spec["y_unit"]],
                "rows": item["rows"],
                "notice": "人工核对的图上标注或图像估计，不是原始测量。",
            },
            ensure_ascii=False,
        )
        block = next(block for block in index["blocks"] if spec["resource"] in block["resources"])
        for start in range(0, len(text), 12000):
            sources.append(
                Evidence(
                    id=f"N{len(sources) + 1}",
                    document_id=document_id,
                    asset_id=asset["id"],
                    filename=asset["relative_path"],
                    source_sha256=asset["sha256"],
                    block_id=block["id"],
                    quote=text[start : start + 12000],
                    locations=[
                        SourceLocation.model_validate(loc)
                        for loc in block["locations"]
                        if loc.get("page")
                    ],
                    kind="chart_data",
                    parse_version=index["version"],
                    source_position=block["locations"],
                )
            )
    warnings = [
        f"{asset['relative_path']}: 新版全文 {index['version']}，未按问题检索裁剪。",
        "图片未作为视觉输入发送；仅提供可读文字、表格和已确认图表数值。",
    ]
    if report["issues"]:
        warnings.append(
            f"{asset['relative_path']}: 处理报告仍有 {len(report['issues'])} 项待核对。"
        )
    return sources, warnings


def evidence_batches(sources, budget=48000):
    batches, current, length = [], [], 0
    for source in sources:
        size = len(source.quote)
        if size > budget:
            raise DomainError("单个来源块超出全文预算，请使用全文出口显式分批。")
        if current and length + size > budget:
            batches.append(current)
            current, length = [], 0
        current.append(source)
        length += size
    if current:
        batches.append(current)
    return batches
