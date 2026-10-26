import json

from backend.core.chat import Evidence
from backend.core.errors import DomainError


class DocumentContext:
    def __init__(self, workspace, reading):
        self.workspace, self.reading = workspace, reading

    def sources(self, project_id, document_ids):
        documents = self.workspace.list_documents(project_id)
        allowed = {doc["id"] for doc in documents}
        if set(document_ids) - allowed:
            raise DomainError("选择的文献不属于当前项目。", "not_found")
        sources, warnings = [], []
        preferences = {}
        if hasattr(self.reading, "data_dir"):
            path = self.reading.data_dir / "parser-next" / project_id / "source-preferences.json"
            if path.exists():
                preferences = json.loads(path.read_text("utf-8"))
        for doc in documents:
            if document_ids and doc["id"] not in document_ids:
                continue
            preference = preferences.get(doc["id"])
            if preference:
                self.reading._read_source(
                    self.reading.repository.asset(project_id, preference["pdf_asset_id"])
                )
                actual = {item["id"]: item["sha256"] for item in doc["assets"]}
                if (
                    actual.get(preference["asset_id"]) != preference["source_sha256"]
                    or actual.get(preference["pdf_asset_id"]) != preference["pdf_sha256"]
                ):
                    raise DomainError(
                        "已确认的原生正文与 PDF 版本发生变化，请重新核对来源优先设置。"
                    )
                warnings.append("使用用户确认同版的原生正文；PDF 仅供核对，未猜测对应页码。")
            for asset in doc["assets"]:
                if preference and asset["id"] == preference["pdf_asset_id"]:
                    continue
                from backend.parsing_next.context import active_sources

                full = (
                    active_sources(self.reading, project_id, doc["id"], asset)
                    if hasattr(self.reading, "data_dir")
                    else None
                )
                if full is not None:
                    for source in full[0]:
                        source.id = f"E{len(sources) + 1}"
                        sources.append(source)
                    warnings.extend(full[1])
                    continue
                if self.reading.status(project_id, asset["id"])["status"] != "ready":
                    warnings.append(f"{asset['relative_path']} 尚未完成有效解析，未参与回答。")
                    continue
                content = self.reading.content(project_id, asset["id"])
                warnings.extend(
                    f"{asset['relative_path']}: {warning}" for warning in content.warnings
                )
                for block in content.blocks:
                    text = block.text
                    if block.cells:
                        text += "\n" + "\n".join(
                            " | ".join(cell.text for cell in block.cells if cell.row == row)
                            for row in range(block.rows)
                        )
                    for start in range(0, len(text), 2500):
                        quote = text[start : start + 2500].strip()
                        if quote:
                            sources.append(
                                Evidence(
                                    id=f"E{len(sources) + 1}",
                                    document_id=doc["id"],
                                    asset_id=asset["id"],
                                    filename=asset["relative_path"],
                                    source_sha256=asset["sha256"],
                                    block_id=block.id,
                                    quote=quote,
                                    locations=block.locations,
                                    kind=block.kind,
                                )
                            )
        return sources, warnings
