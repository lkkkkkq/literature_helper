"""Markdown is the content store; JSON contains only provenance and processing state."""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from backend.core.errors import DomainError


def safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()) or candidate == root.resolve():
        raise DomainError("资源路径不在当前解析版本内。")
    return candidate


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    temporary.replace(path)


class Bundle:
    def __init__(self, root: Path, source: Path, version: str | None = None):
        self.root = root
        self.source = source
        self.version = version or str(uuid.uuid4())
        self.entries = []
        self.parts = []
        self.offset = 0
        self.issues = []
        self.dependencies = []
        self.root.mkdir(parents=True, exist_ok=False)
        for name in ("images", "chart-data", "attachments"):
            (root / name).mkdir()

    def add(self, markdown, *, kind="text", locations=None, resources=None, **metadata):
        markdown = markdown.replace("\r\n", "\n").replace("\r", "\n")
        identifier = f"{self.version}:E{len(self.entries) + 1:05d}"
        text = f"<!-- evidence:{identifier} -->\n{markdown.strip()}\n\n"
        entry = {
            "id": identifier,
            "kind": kind,
            "start": self.offset,
            "end": self.offset + len(text),
            "locations": locations or [],
            "resources": resources or [],
            **metadata,
        }
        self.entries.append(entry)
        self.parts.append(text)
        self.offset += len(text)
        return identifier

    def finish(self, *, engine, source_sha256, pages=None, **metadata):
        markdown = "".join(self.parts)
        if not markdown.strip():
            raise DomainError("没有生成可阅读内容，保留上一可用版本。")
        for entry in self.entries:
            for resource in entry["resources"]:
                if not safe_child(self.root, resource).is_file():
                    self.issues.append(
                        {"kind": "missing_resource", "block": entry["id"], "resource": resource}
                    )
        (self.root / "paper.md").write_text(markdown, encoding="utf-8", newline="")
        write_json(
            self.root / "sources.json",
            {
                "format": 2,
                "version": self.version,
                "filename": self.source.name,
                "source_sha256": source_sha256,
                "offset_unit": "unicode_codepoints",
                "blocks": self.entries,
            },
        )
        report = {
            "version": self.version,
            "engine": engine,
            "source_sha256": source_sha256,
            "created_at": datetime.now(UTC).isoformat(),
            "pages": pages,
            "issues": self.issues,
            "content_reviewed": False,
            "dependencies": self.dependencies,
            "markdown_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
            "status": "needs_review" if self.issues else "generated",
            **metadata,
        }
        write_json(self.root / "parse-report.json", report)
        return report


def load_bundle(root: Path):
    index = json.loads((root / "sources.json").read_text(encoding="utf-8"))
    report = json.loads((root / "parse-report.json").read_text(encoding="utf-8"))
    markdown = (root / "paper.md").read_text(encoding="utf-8")
    if hashlib.sha256(markdown.encode()).hexdigest() != report["markdown_sha256"]:
        raise DomainError("原始解析产物摘要不一致，不能使用被覆盖的来源。")
    return markdown, index, report


def fulltext_batches(root: Path, budget: int):
    """Explicit complete coverage, with no ranking, retrieval, or silent truncation."""
    if budget < 256:
        raise DomainError("全文分批预算至少为 256 字符。")
    markdown, index, _ = load_bundle(root)
    revisions = {}
    for path in sorted((root / "corrections").glob("*.json")):
        revision = json.loads(path.read_text(encoding="utf-8"))
        revisions[revision["block_id"]] = revision["markdown"]
    expected = []
    chart_rows = {}
    for path in sorted((root / "chart-data").glob("revision-*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        spec = item["specification"]
        chart_rows[spec["resource"], spec["panel"], spec["series"]] = item
    batches, current, coverage = [], "", []
    for block in index["blocks"]:
        text = markdown[block["start"] : block["end"]]
        if block["id"] in revisions:
            text = f"<!-- evidence:{block['id']} -->\n{revisions[block['id']]}\n\n"
        for resource in block["resources"]:
            if resource.startswith("chart-data/") and resource.endswith("-native.json"):
                text += "\n原生图表缓存（需核对）：\n" + safe_child(root, resource).read_text(
                    "utf-8"
                )
            for (name, panel, series), item in chart_rows.items():
                if name == resource and item["specification"]["confirmed"]:
                    text += "\n已确认图表数据（图上标注／图像估计）：\n" + json.dumps(
                        {
                            "panel": panel,
                            "series": series,
                            "specification": item["specification"],
                            "rows": item["rows"],
                        },
                        ensure_ascii=False,
                    )
        expected.append(text)
        if len(text) > budget:
            if current:
                batches.append({"text": current, "evidence_ids": coverage})
                current, coverage = "", []
            for start in range(0, len(text), budget):
                batches.append(
                    {
                        "text": text[start : start + budget],
                        "evidence_ids": [block["id"]],
                        "block_continuation": True,
                    }
                )
        else:
            if len(current) + len(text) > budget:
                batches.append({"text": current, "evidence_ids": coverage})
                current, coverage = "", []
            current += text
            coverage.append(block["id"])
    if current:
        batches.append({"text": current, "evidence_ids": coverage})
    return {
        "version": index["version"],
        "budget_chars": budget,
        "batches": batches,
        "complete": "".join(item["text"] for item in batches) == "".join(expected),
        "corrected_blocks": list(revisions),
        "visual_content_included": False,
        "notice": "图片路径不是图像输入；图像需另行读取。超预算分批未自动调用模型。",
    }


def valid_id(value):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise DomainError("无效的解析记录标识。")
    return value
