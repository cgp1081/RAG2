from __future__ import annotations

import uuid

import pytest

from backend.app.routers import structured as structured_router
from backend.structured.query_service import ColumnMeta, GuardViolation, QueryResult, TableRow


class FakeQueryService:
    def __init__(self, result: QueryResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    def execute(self, query: str, tenant_id: uuid.UUID, table_name: str) -> QueryResult:
        if self._error:
            raise self._error
        assert self._result is not None
        return self._result


@pytest.mark.asyncio
async def test_structured_query_success(app, async_client, test_settings, monkeypatch):
    log_id = uuid.uuid4()
    result = QueryResult(
        table_id=uuid.uuid4(),
        table_name="employees",
        columns=[ColumnMeta(name="id", data_type="integer")],
        rows=[TableRow(values={"id": 1})],
        row_count=1,
        execution_ms=10.0,
        log_id=log_id,
    )

    monkeypatch.setattr(
        structured_router,
        "build_query_service",
        lambda settings, session: FakeQueryService(result=result),
    )

    body = {
        "tenant_id": str(uuid.uuid4()),
        "table_name": "employees",
        "sql": "SELECT id FROM employees LIMIT 5",
    }
    response = await async_client.post(
        "/structured/query",
        json=body,
        headers={"X-Admin-API-Key": test_settings.admin_api_key},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 1
    assert payload["rows"][0]["id"] == 1
    assert payload["log_id"] == str(log_id)


@pytest.mark.asyncio
async def test_structured_query_guard_failure(app, async_client, test_settings, monkeypatch):
    monkeypatch.setattr(
        structured_router,
        "build_query_service",
        lambda settings, session: FakeQueryService(error=GuardViolation("blocked")),
    )

    body = {
        "tenant_id": str(uuid.uuid4()),
        "table_name": "employees",
        "sql": "UPDATE employees SET name='Alice'",
    }
    response = await async_client.post(
        "/structured/query",
        json=body,
        headers={"X-Admin-API-Key": test_settings.admin_api_key},
    )

    assert response.status_code == 400
    assert "blocked" in response.json()["detail"]


@pytest.mark.asyncio
async def test_structured_query_missing_admin_key_returns_401(app, async_client):
    response = await async_client.post(
        "/structured/query",
        json={
            "tenant_id": str(uuid.uuid4()),
            "table_name": "employees",
            "sql": "SELECT 1 LIMIT 1",
        },
    )

    assert response.status_code == 401
