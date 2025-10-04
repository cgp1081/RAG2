"""API routers for the backend service."""
from fastapi import APIRouter, Depends

from ..config import Settings, settings_dependency
from .chat import router as chat_router, require_chat_api_key
from .ingestion import router as ingestion_router, require_admin_api_key
from .retrieval import router as retrieval_router

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
    "require_admin_api_key",
    "require_chat_api_key",
]
