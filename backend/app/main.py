"""FastAPI entrypoint for the RAG Platform API.

The service exposes `/healthz` for quick readiness checks and sources its
configuration from `backend.app.config`. JSON structured logging is initialised
via `backend.app.logging` so additional modules can emit consistent telemetry.
"""
from __future__ import annotations

from fastapi import FastAPI

from backend.db.session import init_engine

from .config import get_settings
from .middleware import TracingMiddleware
from .logging import RequestLoggingMiddleware, configure_logging, get_logger
from .observability import configure_tracing, init_metrics
from .routers import chat_router, health_router, retrieval_router, structured_router
from .routers.ingestion import router as admin_router
from .routers.metrics import router as metrics_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""

    settings = get_settings()
    configure_logging(settings.log_level)
    init_engine(settings)
    logger = get_logger(__name__)

    app = FastAPI(title="RAG Platform API", version=settings.app_version)
    app.add_middleware(TracingMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(health_router, prefix="")
    app.include_router(admin_router)
    app.include_router(structured_router)
    app.include_router(chat_router)
    app.include_router(retrieval_router)

    observability = settings.observability_config()
    registry = init_metrics(settings)
    if registry is not None and observability.prometheus_enabled:
        app.include_router(metrics_router)

    if settings.admin_api_key is None:
        logger.warning("admin.api.disabled", reason="missing API key")

    configure_tracing(settings, app)

    return app


app = create_app()


__all__ = ["app", "create_app"]
