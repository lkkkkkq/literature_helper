from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/projects/{project_id}/plugins")


class Toggle(BaseModel):
    enabled: bool


@router.get("")
def plugins(project_id: str, request: Request):
    return request.app.state.plugins.list(project_id)


@router.put("/{plugin_id}")
def toggle(project_id: str, plugin_id: str, body: Toggle, request: Request):
    return request.app.state.plugins.set(project_id, plugin_id, body.enabled)
