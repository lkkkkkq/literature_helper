from fastapi import APIRouter, Header, Request

from backend.core.chat import ModelProfileInput, Question

router = APIRouter(prefix="/api/projects/{project_id}")


@router.get("/model")
def profile(project_id: str, request: Request):
    return request.app.state.chat.repository.profile(project_id)


@router.put("/model")
def save_profile(project_id: str, body: ModelProfileInput, request: Request):
    return request.app.state.chat.repository.save_profile(project_id, body)


@router.post("/model/test")
def test_model(project_id: str, request: Request, x_model_key: str = Header(default="")):
    return request.app.state.chat.test(project_id, x_model_key)


@router.get("/sessions/{session_id}/answers")
def history(project_id: str, session_id: str, request: Request):
    return request.app.state.chat.repository.history(project_id, session_id)


@router.post("/sessions/{session_id}/answers")
def answer(
    project_id: str,
    session_id: str,
    body: Question,
    request: Request,
    x_model_key: str = Header(default=""),
):
    return request.app.state.chat.ask(project_id, session_id, body, x_model_key)
