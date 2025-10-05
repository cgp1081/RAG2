"""Voice telephony endpoints for Twilio integration."""
from __future__ import annotations

import base64
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

try:  # pragma: no cover - optional dependency
    from twilio.request_validator import RequestValidator
except Exception:  # pragma: no cover - fallback when twilio not installed
    class RequestValidator:  # type: ignore
        def __init__(self, token: str) -> None:
            self.token = token

        def validate(self, url: str, params: dict, signature: str) -> bool:
            return True

from backend.app.config import Settings, settings_dependency
from backend.db.models import Tenant
from backend.db.session import SessionLocal
from backend.rag.dependencies import get_rag_pipeline
from backend.rag.pipeline import RAGPipeline
from backend.voice.call_handler import (
    AssistantTurn,
    VoiceCallHandler,
    build_default_voice_handler,
)

router = APIRouter(prefix="/voice", tags=["voice"])


class StreamMedia(BaseModel):
    payload: str


class StreamEvent(BaseModel):
    event: str
    media: StreamMedia | None = None


def require_voice_enabled(settings: Settings = Depends(settings_dependency)) -> Settings:
    cfg = settings.voice_config()
    if not cfg.twilio_account_sid or not cfg.twilio_auth_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Voice not configured")
    return settings


def _resolve_tenant_id(slug_or_uuid: str | None, settings: Settings) -> uuid.UUID:
    if slug_or_uuid:
        try:
            return uuid.UUID(slug_or_uuid)
        except ValueError:
            pass
    slug = slug_or_uuid or settings.ingest_default_tenant
    if not slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant not provided")
    with SessionLocal() as session:
        stmt = (
            session.query(Tenant)
            .filter(Tenant.slug == slug)
        )
        tenant = stmt.scalar()
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        return tenant.id


async def get_voice_handler(
    settings: Settings = Depends(settings_dependency),
    pipeline: RAGPipeline = Depends(get_rag_pipeline),
) -> VoiceCallHandler:
    return build_default_voice_handler(settings, pipeline)


@router.post("/inbound")
async def inbound_call(
    request: Request,
    settings: Settings = Depends(require_voice_enabled),
    handler: VoiceCallHandler = Depends(get_voice_handler),
) -> PlainTextResponse:
    form = await request.form()
    call_sid = form.get("CallSid")
    if not call_sid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CallSid missing")

    signature = request.headers.get("X-Twilio-Signature")
    validator = RequestValidator(settings.voice_config().twilio_auth_token)
    if signature:
        url = str(request.url)
        if not validator.validate(url, dict(form), signature):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

    tenant_id = _resolve_tenant_id(form.get("Tenant"), settings)
    metadata = {
        key: value
        for key, value in (
            ("caller_city", form.get("CallerCity")),
            ("caller_state", form.get("CallerState")),
            ("caller_country", form.get("CallerCountry")),
            ("caller_zip", form.get("CallerZip")),
        )
        if value
    }

    response_xml, session_id = handler.handle_inbound_call(
        call_sid=call_sid,
        tenant_id=str(tenant_id),
        caller_number=form.get("From"),
        callee_number=form.get("To"),
        metadata=metadata,
    )
    return PlainTextResponse(response_xml, media_type="application/xml")


@router.post("/events")
async def voice_events(
    payload: dict,
    settings: Settings = Depends(settings_dependency),
    handler: VoiceCallHandler = Depends(get_voice_handler),
) -> Response:
    call_sid = payload.get("CallSid")
    session_id_value = payload.get("CallSessionId") or payload.get("session_id")
    if not call_sid or not session_id_value:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    try:
        session_id = uuid.UUID(session_id_value)
    except ValueError:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    metadata = {
        key: payload.get(key)
        for key in ["CallDuration", "CallerCity", "CallerState", "CallerCountry"]
        if payload.get(key) is not None
    }

    handler.handle_status_callback(
        session_id=session_id,
        status=payload.get("CallStatus", "in-progress"),
        error=payload.get("ErrorMessage"),
        metadata=metadata,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/stream/{session_id}")
async def voice_stream(
    session_id: uuid.UUID,
    payload: StreamEvent,
    settings: Settings = Depends(settings_dependency),
    handler: VoiceCallHandler = Depends(get_voice_handler),
) -> dict:
    if payload.event != "media" or not payload.media:
        return {"status": "ignored"}

    try:
        audio_bytes = base64.b64decode(payload.media.payload)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid media payload: {exc}")

    call_session = handler.get_session(session_id)
    if call_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call session not found")

    async def single_chunk() -> AsyncIterator[bytes]:
        yield audio_bytes

    tenant_id = str(call_session.tenant_id)
    call_sid = call_session.twilio_call_sid
    turns: list[AssistantTurn] = await handler.process_stream(
        session_id=session_id,
        tenant_id=tenant_id,
        call_sid=call_sid,
        audio_stream=single_chunk(),
    )
    return {
        "status": "ok",
        "responses": [turn.text for turn in turns],
    }


__all__ = ["router"]
