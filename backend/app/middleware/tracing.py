"""Tracing middleware that attaches trace and tenant context to requests."""
from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp


class TracingMiddleware(BaseHTTPMiddleware):
    """Ensure each request carries a trace identifier and optional tenant context."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._logger = structlog.get_logger("backend.tracing")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
        tenant_id = request.headers.get("X-Tenant-Id")

        content_type = request.headers.get("content-type", "")
        if tenant_id is None and content_type.startswith("application/json"):
            body_bytes = await request.body()
            if body_bytes:
                try:
                    payload = json.loads(body_bytes)
                    if isinstance(payload, dict):
                        tenant_id = _extract_tenant_id(payload)
                except json.JSONDecodeError:
                    pass
            request._body = body_bytes  # type: ignore[attr-defined]

        request.state.trace_id = trace_id
        if tenant_id:
            request.state.tenant_id = tenant_id

        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        if tenant_id:
            structlog.contextvars.bind_contextvars(tenant_id=tenant_id)

        try:
            response = await call_next(request)
        except Exception:
            self._logger.exception("trace.error", trace_id=trace_id, tenant_id=tenant_id)
            raise
        finally:
            structlog.contextvars.unbind_contextvars("trace_id")
            if tenant_id:
                structlog.contextvars.unbind_contextvars("tenant_id")

        response.headers.setdefault("X-Trace-Id", trace_id)
        if tenant_id:
            response.headers.setdefault("X-Tenant-Id", tenant_id)
        return response


def _extract_tenant_id(payload: dict[str, Any]) -> str | None:
    keys = ("tenant_id", "tenantId", "tenant")
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


__all__ = ["TracingMiddleware"]
