from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient

from backend.app.config import Settings
from backend.db.models import CallSession, CallTurn, Tenant
from backend.db.session import SessionLocal


class StubStorage:
    def presign(self, object_key: str, *, expires_seconds: int = 3600) -> str:
        return f"https://storage.test/{object_key}?expires={expires_seconds}"

    def upload(self, *args: Any, **kwargs: Any) -> str:  # pragma: no cover - not used here
        return ""


def seed_call(
    *,
    tenant_id: uuid.UUID,
    status: str,
    confidence: float,
    escalated: bool,
    created_offset: timedelta,
    transcript: str,
    storage_key: str | None,
) -> CallSession:
    created_at = datetime.now(timezone.utc) - created_offset
    ended_at = created_at + timedelta(seconds=30)
    call = CallSession(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        twilio_call_sid=f"CA-{uuid.uuid4()}",
        status=status,
        caller_number="+15550000000",
        callee_number="+15550000001",
        confidence=confidence,
        transcript=transcript,
        summary=transcript[:200],
        escalated=escalated,
        created_at=created_at,
        updated_at=ended_at,
        ended_at=ended_at,
        storage_object_key=storage_key,
    )
    return call


@pytest.fixture
def seeded_calls(db_session):
    tenant_a = Tenant(id=uuid.uuid4(), name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(id=uuid.uuid4(), name="Tenant B", slug="tenant-b")
    db_session.add_all([tenant_a, tenant_b])
    db_session.commit()

    call_a1 = seed_call(
        tenant_id=tenant_a.id,
        status="completed",
        confidence=0.9,
        escalated=False,
        created_offset=timedelta(days=1),
        transcript="Transcript A1",
        storage_key="calls/a1.wav",
    )
    call_a2 = seed_call(
        tenant_id=tenant_a.id,
        status="completed",
        confidence=0.4,
        escalated=True,
        created_offset=timedelta(days=2),
        transcript="Transcript A2",
        storage_key=None,
    )
    call_b1 = seed_call(
        tenant_id=tenant_b.id,
        status="running",
        confidence=0.7,
        escalated=False,
        created_offset=timedelta(days=1),
        transcript="Transcript B1",
        storage_key=None,
    )

    db_session.add_all([call_a1, call_a2, call_b1])
    db_session.commit()

    turn = CallTurn(
        session_id=call_a1.id,
        sequence=1,
        speaker="caller",
        text="Hi",
        confidence=0.9,
        started_at=call_a1.created_at,
        ended_at=call_a1.created_at + timedelta(seconds=1),
    )
    db_session.add(turn)
    db_session.commit()

    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "call_a1": call_a1,
        "call_a2": call_a2,
        "call_b1": call_b1,
    }


@pytest.mark.asyncio
async def test_list_calls_filters_by_tenant_and_status(
    async_client: AsyncClient,
    test_settings: Settings,
    seeded_calls,
    monkeypatch,
):
    monkeypatch.setattr("backend.app.routers.calls.build_call_storage_adapter", lambda settings: StubStorage())

    response = await async_client.get(
        "/admin/calls",
        params={"tenant": seeded_calls["tenant_a"].slug, "status": "completed"},
        headers={"X-Admin-API-Key": test_settings.admin_api_key},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2
    assert all(item["tenant_id"] == str(seeded_calls["tenant_a"].id) for item in payload["items"])


@pytest.mark.asyncio
async def test_get_call_detail_includes_presigned_url(
    async_client: AsyncClient,
    test_settings: Settings,
    seeded_calls,
    monkeypatch,
):
    monkeypatch.setattr("backend.app.routers.calls.build_call_storage_adapter", lambda settings: StubStorage())
    target_call = seeded_calls["call_a1"]
    response = await async_client.get(
        f"/admin/calls/{target_call.id}",
        headers={"X-Admin-API-Key": test_settings.admin_api_key},
    )
    assert response.status_code == 200
    detail = response.json()
    assert detail["recording_url"].startswith("https://storage.test/")
    assert len(detail["turns"]) == 1


@pytest.mark.asyncio
async def test_list_calls_requires_admin_key(async_client: AsyncClient, seeded_calls):
    response = await async_client.get("/admin/calls")
    assert response.status_code == 401
