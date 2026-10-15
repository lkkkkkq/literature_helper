from fastapi import APIRouter, Request, Response

from backend.core.documents import ParsedContent, ParseRequest

router = APIRouter(prefix="/api/projects/{project_id}/assets/{asset_id}")


@router.get("/parse")
def status(project_id: str, asset_id: str, request: Request):
    return request.app.state.reading.status(project_id, asset_id)


@router.post("/parse", status_code=202)
def parse(project_id: str, asset_id: str, body: ParseRequest, request: Request):
    return request.app.state.reading.start(project_id, asset_id, body)


@router.get("/content", response_model=ParsedContent)
def content(project_id: str, asset_id: str, request: Request):
    return request.app.state.reading.content(project_id, asset_id)


@router.get("/pdf")
def pdf(project_id: str, asset_id: str, request: Request):
    return Response(
        request.app.state.reading.source(project_id, asset_id),
        media_type="application/pdf",
        headers={"Cache-Control": "no-store"},
    )
