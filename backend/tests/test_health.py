from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health(async_client, test_settings):
    response = await async_client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app_version": test_settings.app_version}
