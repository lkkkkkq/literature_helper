from typing import Literal

from fastapi import APIRouter, Request

from backend.core.reviews import ReviewEdit
from backend.services.exporting import export_snapshot

router = APIRouter(prefix="/api/projects/{project_id}/jobs/{job_id}")


@router.get("/results")
def results(project_id: str, job_id: str, request: Request, version: str = "latest"):
    return request.app.state.reviews.snapshot(project_id, job_id, version)


@router.post("/reviews", status_code=201)
def review(project_id: str, job_id: str, body: ReviewEdit, request: Request):
    return request.app.state.reviews.append(project_id, job_id, body)


@router.get("/export")
def export(
    project_id: str,
    job_id: str,
    request: Request,
    format: Literal["csv", "xlsx"] = "xlsx",
    version: str = "latest",
):
    return export_snapshot(request.app.state.reviews.snapshot(project_id, job_id, version), format)
