"""FastAPI entrypoint for the RAG Platform API.

The service exposes `/healthz` for quick readiness checks and sources its
configuration from `backend.app.config`. JSON structured logging is initialised
via `backend.app.logging` so additional modules can emit consistent telemetry.
"""
from __future__ import annotations

from fastapi import FastAPI

from backend.db.session import init_engine

from .config import get_settings
from .logging import RequestLoggingMiddleware, configure_logging
from .routers import health_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""

    settings = get_settings()
    configure_logging(settings.log_level)
    init_engine(settings)

    app = FastAPI(title="RAG Platform API", version=settings.app_version)
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(health_router, prefix="")

    return app


app = create_app()


__all__ = ["app", "create_app"]
