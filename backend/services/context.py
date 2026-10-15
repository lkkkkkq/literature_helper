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
        for doc in documents:
            if document_ids and doc["id"] not in document_ids:
                continue
            for asset in doc["assets"]:
                if self.reading.status(project_id, asset["id"])["status"] != "ready":
                    warnings.append(f"{asset['relative_path']} 尚未完成有效解析，未参与回答。")
                    continue
                content = self.reading.content(project_id, asset["id"])
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
