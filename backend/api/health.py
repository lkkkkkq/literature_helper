from fastapi import APIRouter, Request

from backend.services.health import HealthStatus

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthStatus)
def health(request: Request) -> HealthStatus:
    return request.app.state.health_service.check()
