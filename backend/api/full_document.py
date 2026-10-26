from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.core.errors import DomainError

router = APIRouter(prefix="/api/projects/{project_id}/assets/{asset_id}/full-document")


class Operation(BaseModel):
    operation: str
    version: str = ""
    payload: dict = Field(default_factory=dict)


@router.post("")
def operate(project_id: str, asset_id: str, body: Operation, request: Request):
    service = request.app.state.full_document
    args = (project_id, asset_id)
    if body.operation == "status":
        return service.status(*args)
    if body.operation == "start":
        return service.start(*args, str(body.payload.get("pages", "all")))
    if body.operation == "cancel":
        return service.cancel(*args)
    if body.operation == "prefer_source":
        return service.prefer_source(*args, body.payload.get("confirmed_same_version"))
    args += (body.version,)
    if body.operation == "content":
        return service.content(*args)
    if body.operation == "resource":
        return service.resource(*args, body.payload.get("name", ""))
    if body.operation == "correct":
        return service.correct(*args, body.payload)
    if body.operation == "charts":
        return service.charts(*args)
    if body.operation == "save_chart":
        return service.save_chart(*args, body.payload)
    if body.operation == "fulltext":
        budget = body.payload.get("budget", 48000)
        if not isinstance(budget, int) or not 256 <= budget <= 2000000:
            raise DomainError("全文预算需在 256 到 2000000 字符之间。")
        return service.fulltext(*args, budget)
    raise DomainError("不支持的新版解析操作。")
