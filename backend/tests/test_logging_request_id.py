from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_logging_request_id(async_client, log_capture):
    response = await async_client.get("/healthz")

    assert response.headers["X-Request-ID"]
    uuid.UUID(response.headers["X-Request-ID"])

    log_entry = next((entry for entry in log_capture if entry.get("event") == "request"), None)
    assert log_entry is not None
    assert log_entry.get("request_id") == response.headers["X-Request-ID"]
    assert log_entry.get("method") == "GET"
    assert log_entry.get("status_code") == 200
