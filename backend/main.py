import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.api.chat import router as chat_router
from backend.api.health import router
from backend.api.jobs import router as jobs_router
from backend.api.plugins import router as plugins_router
from backend.api.reading import router as reading_router
from backend.api.reviews import router as reviews_router
from backend.api.workspace import router as workspace_router
from backend.core.config import Settings
from backend.core.errors import DomainError
from backend.db.database import create_database
from backend.parsers.docling_adapter import DoclingAdapter
from backend.plugins.manager import PluginCatalog
from backend.repositories.chat import ChatRepository
from backend.repositories.health import HealthRepository
from backend.repositories.jobs import JobRepository
from backend.repositories.parsing import ParsingRepository
from backend.repositories.plugins import PluginRepository
from backend.repositories.reviews import ReviewRepository
from backend.repositories.workspace import WorkspaceRepository
from backend.services.chat import ChatService
from backend.services.health import HealthService
from backend.services.jobs import JobService
from backend.services.plugins import PluginService
from backend.services.reading import ReadingService
from backend.services.workspace import WorkspaceService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_database(settings.data_dir)
        app.state.health_service = HealthService(HealthRepository(engine))
        app.state.workspace = WorkspaceService(WorkspaceRepository(engine), settings.data_dir)
        model_dir = os.environ.get(
            "LITEXTRACT_MODEL_DIR",
            str(Path(__file__).resolve().parents[1] / ".local/docling-models"),
        )
        app.state.reading = ReadingService(
            ParsingRepository(engine),
            settings.data_dir,
            DoclingAdapter(Path(model_dir) if model_dir else None),
        )
        app.state.chat = ChatService(
            ChatRepository(engine), WorkspaceRepository(engine), app.state.reading
        )
        app.state.jobs = JobService(JobRepository(engine), app.state.chat, settings.data_dir)
        app.state.plugins = PluginService(PluginRepository(engine), PluginCatalog())
        app.state.jobs.plugins = app.state.plugins
        app.state.reviews = ReviewRepository(engine)
        try:
            yield
        finally:
            app.state.jobs.close()
            app.state.reading.close()
            engine.dispose()

    app = FastAPI(
        title="LitExtract v2",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {settings.api_token}"
        if not secrets.compare_digest(supplied.encode(), expected.encode()):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

    app.include_router(router)
    app.include_router(workspace_router)
    app.include_router(reading_router)
    app.include_router(chat_router)
    app.include_router(jobs_router)
    app.include_router(reviews_router)
    app.include_router(plugins_router)

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, error: DomainError):
        status = {"not_found": 404, "conflict": 409}.get(error.code, 400)
        return JSONResponse({"detail": str(error), "code": error.code}, status_code=status)

    return app
