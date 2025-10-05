"""API routers for the backend service."""
from fastapi import APIRouter, Depends

from ..config import Settings, settings_dependency
from .chat import require_chat_api_key, router as chat_router
from .ingestion import require_admin_api_key, router as ingestion_router
from .calls import router as calls_router
from .metrics import router as metrics_router
from .retrieval import router as retrieval_router
from .structured import router as structured_router

health_router = APIRouter()


@health_router.get("/healthz", tags=["system"])
async def health(settings: Settings = Depends(settings_dependency)) -> dict[str, str]:
    """Basic readiness probe with version info."""

    return {"status": "ok", "app_version": settings.app_version}


__all__ = [
    "health_router",
    "ingestion_router",
    "retrieval_router",
    "chat_router",
    "structured_router",
    "calls_router",
    "metrics_router",
    "require_admin_api_key",
    "require_chat_api_key",
]
