from fastapi import APIRouter, Request, Response

from backend.core.schemas import MessageCreate, ProjectCreate, Rename, ScanConfirm, SessionCreate

router = APIRouter(prefix="/api/projects")


@router.get("")
def projects(request: Request):
    return request.app.state.workspace.list_projects()


@router.post("", status_code=201)
def create_project(body: ProjectCreate, request: Request):
    return request.app.state.workspace.create_project(body)


@router.get("/{project_id}")
def project(project_id: str, request: Request):
    return request.app.state.workspace.get_project(project_id)


@router.patch("/{project_id}")
def rename_project(project_id: str, body: Rename, request: Request):
    return request.app.state.workspace.rename_project(project_id, body.name)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, request: Request):
    request.app.state.workspace.delete_project(project_id)
    return Response(status_code=204)


@router.post("/{project_id}/scan")
def scan(project_id: str, request: Request):
    return request.app.state.workspace.scan(project_id)


@router.get("/{project_id}/scan")
def draft(project_id: str, request: Request):
    return request.app.state.workspace.draft(project_id)


@router.post("/{project_id}/scan/confirm")
def confirm_scan(project_id: str, body: ScanConfirm, request: Request):
    return request.app.state.workspace.confirm_scan(project_id, body)


@router.get("/{project_id}/documents")
def documents(project_id: str, request: Request):
    return request.app.state.workspace.documents(project_id)


@router.get("/{project_id}/documents/{document_id}")
def document(project_id: str, document_id: str, request: Request):
    return request.app.state.workspace.document(project_id, document_id)


@router.get("/{project_id}/sessions")
def sessions(project_id: str, request: Request):
    return request.app.state.workspace.sessions(project_id)


@router.post("/{project_id}/sessions", status_code=201)
def create_session(project_id: str, body: SessionCreate, request: Request):
    return request.app.state.workspace.create_session(project_id, body.name)


@router.patch("/{project_id}/sessions/{session_id}")
def rename_session(project_id: str, session_id: str, body: Rename, request: Request):
    return request.app.state.workspace.rename_session(project_id, session_id, body.name)


@router.delete("/{project_id}/sessions/{session_id}", status_code=204)
def delete_session(project_id: str, session_id: str, request: Request):
    request.app.state.workspace.delete_session(project_id, session_id)
    return Response(status_code=204)


@router.get("/{project_id}/sessions/{session_id}/messages")
def messages(project_id: str, session_id: str, request: Request):
    return request.app.state.workspace.messages(project_id, session_id)


@router.post("/{project_id}/sessions/{session_id}/messages", status_code=201)
def add_message(project_id: str, session_id: str, body: MessageCreate, request: Request):
    return request.app.state.workspace.add_message(project_id, session_id, body.content)
