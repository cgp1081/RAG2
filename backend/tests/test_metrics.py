from __future__ import annotations

import pytest
from httpx import AsyncClient

from backend.app.config import Settings, settings_dependency
from backend.app.main import create_app


@pytest.mark.asyncio
async def test_metrics_endpoint_available(async_client: AsyncClient):
    response = await async_client.get("/metrics")

    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert "rag_pipeline_duration_seconds" in response.text


@pytest.mark.asyncio
async def test_metrics_endpoint_disabled(test_settings: Settings, monkeypatch: pytest.MonkeyPatch):
    disabled_settings = test_settings.model_copy(
        update={
            "prometheus_enabled": False,
            "observability_enabled": True,
        }
    )

    monkeypatch.setattr("backend.app.main.get_settings", lambda: disabled_settings)

    application = create_app()
    application.dependency_overrides[settings_dependency] = lambda: disabled_settings

    async with AsyncClient(app=application, base_url="http://testserver") as client:
        response = await client.get("/metrics")

    assert response.status_code == 404
