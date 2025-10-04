"""Prometheus metrics endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from backend.app.config import Settings, settings_dependency
from backend.app.observability import CONTENT_TYPE_LATEST, generate_latest, init_metrics

router = APIRouter(tags=["observability"], include_in_schema=False)


@router.get("/metrics")
async def metrics(settings: Settings = Depends(settings_dependency)) -> PlainTextResponse:
    registry = init_metrics(settings)
    if registry is None:
        raise HTTPException(status_code=404, detail="Prometheus metrics disabled")

    payload = generate_latest(registry).decode("utf-8")
    return PlainTextResponse(content=payload, media_type=CONTENT_TYPE_LATEST)


__all__ = ["router"]
