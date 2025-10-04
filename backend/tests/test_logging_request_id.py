from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_logging_request_id(async_client, log_capture):
    response = await async_client.get("/healthz", headers={"X-Tenant-Id": "tenant-test"})

    assert response.headers["X-Request-ID"]
    uuid.UUID(response.headers["X-Request-ID"])
    assert response.headers["X-Trace-Id"]
    uuid.UUID(response.headers["X-Trace-Id"])

    log_entry = next((entry for entry in log_capture if entry.get("event") == "request"), None)
    assert log_entry is not None
    assert log_entry.get("request_id") == response.headers["X-Request-ID"]
    assert log_entry.get("method") == "GET"
    assert log_entry.get("status_code") == 200
    assert log_entry.get("trace_id") == response.headers["X-Trace-Id"]
    assert log_entry.get("tenant_id") == "tenant-test"
