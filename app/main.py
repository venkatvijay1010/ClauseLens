"""DocuDiff application factory and static demo entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import Settings, get_settings
from app.db import Database
from app.request_limits import RequestBodyLimitMiddleware
from app.services.assessment import (
    HeuristicAssessmentProvider,
    OpenAIAssessmentProvider,
    SafeAssessmentService,
)


def _assessment_service(settings: Settings) -> SafeAssessmentService:
    fallback = HeuristicAssessmentProvider()
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return SafeAssessmentService(
            OpenAIAssessmentProvider(
                settings.openai_api_key, settings.openai_model, settings.llm_timeout_seconds
            ),
            fallback=fallback,
        )
    return SafeAssessmentService(fallback)


def create_app(
    database_url: str | None = None,
    settings: Settings | None = None,
    create_schema_for_tests: bool = False,
) -> FastAPI:
    active_settings = settings or get_settings()
    database = Database(database_url or active_settings.database_url)
    static_dir = Path(__file__).parent / "static"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active_settings.upload_dir.mkdir(parents=True, exist_ok=True)
        if create_schema_for_tests:
            database.create_all()
        yield
        database.dispose()

    app = FastAPI(
        title="DocuDiff",
        version="0.1.0",
        description="Evidence-backed document version comparison and change review.",
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.db = database
    app.state.assessment_service = _assessment_service(active_settings)
    # Keep enough headroom for multipart boundaries while limiting the raw ASGI body
    # before Starlette can parse or spool an uploaded file.
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=active_settings.max_upload_bytes + 64 * 1024,
    )
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/health", tags=["Health"])
    def health(request: Request) -> dict[str, str]:
        try:
            request.app.state.db.healthcheck()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable.") from exc
        return {"status": "ok", "assessment_provider": request.app.state.settings.llm_provider}

    return app


app = create_app()
