from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI
from starlette.testclient import TestClient
from structlog.testing import capture_logs

from backend.app.logging import configure_logging
from backend.app.middleware import TracingMiddleware


def test_tracing_middleware_sets_headers_and_context() -> None:
    configure_logging("INFO")
    app = FastAPI()
    app.add_middleware(TracingMiddleware)
    logger = structlog.get_logger("test.trace")

    @app.get("/ping")
    async def _endpoint() -> dict[str, str]:
        logger.info("in_route")
        return {"status": "ok"}

    with capture_logs() as logs:
        with TestClient(app) as client:
            response = client.get("/ping", headers={"X-Tenant-Id": "tenant-abc"})

    trace_header = response.headers.get("X-Trace-Id")
    assert trace_header is not None
    uuid.UUID(trace_header)
    assert response.headers.get("X-Tenant-Id") == "tenant-abc"

    log_entry = next(entry for entry in logs if entry.get("event") == "in_route")
    assert log_entry["trace_id"] == trace_header
    assert log_entry["tenant_id"] == "tenant-abc"
