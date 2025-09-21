"""API routers for the backend service."""
from fastapi import APIRouter, Depends

from ..config import Settings, settings_dependency

health_router = APIRouter()


@health_router.get("/healthz", tags=["system"])
async def health(settings: Settings = Depends(settings_dependency)) -> dict[str, str]:
    """Basic readiness probe with version info."""

    return {"status": "ok", "app_version": settings.app_version}


__all__ = ["health_router"]
