import asyncio
import json

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.extraction import ConfirmPlan, DesignRequest

router = APIRouter(prefix="/api/projects/{project_id}")


class RouteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


class TemplateRequest(BaseModel):
    plugin_id: str


@router.post("/sessions/{session_id}/templates")
def template(project_id: str, session_id: str, body: TemplateRequest, request: Request):
    return request.app.state.jobs.template(project_id, session_id, body.plugin_id)


@router.post("/route")
def route(
    project_id: str, body: RouteRequest, request: Request, x_model_key: str = Header(default="")
):
    return request.app.state.jobs.route(project_id, body.text, x_model_key)


@router.get("/sessions/{session_id}/plans")
def plans(project_id: str, session_id: str, request: Request):
    return request.app.state.jobs.repository.plans(project_id, session_id)


@router.post("/sessions/{session_id}/plans")
def design(
    project_id: str,
    session_id: str,
    body: DesignRequest,
    request: Request,
    x_model_key: str = Header(default=""),
):
    return request.app.state.jobs.design(project_id, session_id, body, x_model_key)


@router.post("/sessions/{session_id}/jobs", status_code=201)
def confirm(
    project_id: str,
    session_id: str,
    body: ConfirmPlan,
    request: Request,
    x_model_key: str = Header(default=""),
):
    return request.app.state.jobs.confirm(project_id, session_id, body, x_model_key)


@router.get("/sessions/{session_id}/jobs")
def jobs(project_id: str, session_id: str, request: Request):
    return request.app.state.jobs.repository.list(project_id, session_id)


@router.get("/jobs/{job_id}")
def job(project_id: str, job_id: str, request: Request):
    return request.app.state.jobs.repository.get(project_id, job_id)


@router.post("/jobs/{job_id}/cancel")
def cancel(project_id: str, job_id: str, request: Request):
    return request.app.state.jobs.cancel(project_id, job_id)


@router.post("/jobs/{job_id}/resume")
def resume(project_id: str, job_id: str, request: Request, x_model_key: str = Header(default="")):
    return request.app.state.jobs.resume(project_id, job_id, x_model_key)


@router.get("/jobs/{job_id}/records")
def records(project_id: str, job_id: str, request: Request):
    return request.app.state.jobs.repository.records(project_id, job_id)


@router.get("/jobs/{job_id}/events")
async def events(project_id: str, job_id: str, request: Request):
    repository = request.app.state.jobs.repository
    repository.get(project_id, job_id)

    async def stream():
        last = ""
        while not await request.is_disconnected():
            snapshot = repository.get(project_id, job_id)
            value = json.dumps(snapshot, ensure_ascii=False)
            if value != last:
                yield f"event: progress\ndata: {value}\n\n"
                last = value
            if snapshot["status"] not in {"pending", "running"}:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"}
    )
