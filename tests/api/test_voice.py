from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from backend.app.config import Settings
from backend.app.routers import voice as voice_router
from backend.db.models import Tenant
from backend.voice.call_handler import VoiceCallHandler


class StubVoiceHandler:
    def __init__(self) -> None:
        self.sessions: dict[str, uuid.UUID] = {}

    def handle_inbound_call(self, *, call_sid: str, tenant_id: str, caller_number: str | None, callee_number: str | None):
        session_id = uuid.uuid4()
        self.sessions[call_sid] = session_id
        return "<Response><Start><Stream url=\"/voice/stream/{}\"/></Start></Response>".format(session_id), session_id

    def handle_status_callback(self, *, session_id: uuid.UUID, status: str, error: str | None = None) -> None:
        return None

    def get_session(self, session_id: uuid.UUID):
        class Dummy:
            def __init__(self, sid: uuid.UUID) -> None:
                self.id = sid
                self.tenant_id = uuid.uuid4()
                self.twilio_call_sid = "SIM"
        return Dummy(session_id)

    async def process_stream(self, **kwargs):  # pragma: no cover - not used in these tests
        return []


@pytest.mark.asyncio
async def test_voice_inbound_and_events(
    async_client: AsyncClient,
    test_settings: Settings,
    db_session,
):
    test_settings.twilio_account_sid = "AC123"
    test_settings.twilio_auth_token = "secret"
    tenant = Tenant(id=uuid.uuid4(), name="Voice", slug="voice")
    db_session.add(tenant)
    db_session.commit()

    app: FastAPI = async_client.app  # type: ignore[attr-defined]

    handler = StubVoiceHandler()

    async def override_voice_handler():
        return handler

    app.dependency_overrides[voice_router.require_voice_enabled] = lambda: test_settings
    app.dependency_overrides[voice_router.get_voice_handler] = override_voice_handler

    class FakeValidator:
        def __init__(self, token: str) -> None:
            self.token = token

        def validate(self, url: str, params: dict, signature: str) -> bool:
            return True

    voice_router.RequestValidator = FakeValidator  # type: ignore

    response = await async_client.post(
        "/voice/inbound",
        data={"CallSid": "CA123", "From": "+15550001111", "To": "+15550009999", "Tenant": str(tenant.id)},
        headers={"X-Twilio-Signature": "signature"},
    )
    assert response.status_code == 200
    assert "<Start>" in response.text

    session_id = handler.sessions["CA123"]
    event_response = await async_client.post(
        "/voice/events",
        json={"CallSid": "CA123", "CallSessionId": str(session_id), "CallStatus": "completed"},
    )
    assert event_response.status_code == 204

    app.dependency_overrides.clear()
