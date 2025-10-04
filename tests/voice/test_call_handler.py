from __future__ import annotations

import asyncio
import uuid
from typing import AsyncIterator

import pytest

from backend.app.config import Settings
from backend.db.models import CallTurn, Tenant
from backend.db.session import SessionLocal
from backend.rag.pipeline import RAGResult, TokenUsage
from backend.voice.call_handler import AssistantTurn, CallSessionManager, VoiceCallHandler
from backend.voice.stt_adapter import TranscriptSegment


class StubPipeline:
    def __init__(self, answer: str = "Acknowledged") -> None:
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    async def generate_answer(self, query: str, tenant_id: str, **_: object) -> RAGResult:
        self.calls.append((query, tenant_id))
        return RAGResult(
            answer=self.answer,
            model="stub",
            prompt="",
            prompt_id="stub",
            citations=[],
            token_usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            latency_ms=5.0,
            table=None,
        )


class StubSTT:
    def __init__(self, segments: list[TranscriptSegment]) -> None:
        self._segments = segments

    async def stream_transcript(self, stream: AsyncIterator[bytes], *, language: str = "en-US"):
        # Consume stream to mimic adapter behaviour
        async for _ in stream:
            break
        for segment in self._segments:
            yield segment


class StubTTS:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        self.calls.append(text)
        return text.encode("utf-8")


async def _empty_audio_stream() -> AsyncIterator[bytes]:
    if False:
        yield b""


@pytest.fixture
def tenant_id(db_session) -> uuid.UUID:
    tenant = Tenant(id=uuid.uuid4(), name="Voice", slug="voice")
    db_session.add(tenant)
    db_session.commit()
    return tenant.id


@pytest.fixture
def session_manager() -> CallSessionManager:
    return CallSessionManager(SessionLocal)


@pytest.fixture
def base_handler(test_settings: Settings, session_manager: CallSessionManager) -> VoiceCallHandler:
    pipeline = StubPipeline()
    stt = StubSTT([])
    tts = StubTTS()
    return VoiceCallHandler(
        session_manager=session_manager,
        rag_pipeline=pipeline,
        stt_adapter=stt,
        tts_adapter=tts,
        settings=test_settings,
    )


def test_inbound_call_creates_session_and_returns_twiml(
    test_settings: Settings,
    session_manager: CallSessionManager,
    tenant_id: uuid.UUID,
):
    pipeline = StubPipeline()
    stt = StubSTT([])
    tts = StubTTS()
    handler = VoiceCallHandler(
        session_manager=session_manager,
        rag_pipeline=pipeline,
        stt_adapter=stt,
        tts_adapter=tts,
        settings=test_settings,
    )
    xml, session_uuid = handler.handle_inbound_call(
        call_sid="CA123",
        tenant_id=str(tenant_id),
        caller_number="+15550001111",
        callee_number="+15550009999",
    )
    assert "<Start>" in xml or "<Start/>" in xml
    stored = session_manager.get_session(session_uuid)
    assert stored is not None
    assert stored.twilio_call_sid == "CA123"
    assert stored.status == "initiated"


@pytest.mark.asyncio
async def test_process_stream_appends_turns_and_calls_pipeline(
    test_settings: Settings,
    session_manager: CallSessionManager,
    tenant_id: uuid.UUID,
):
    pipeline = StubPipeline(answer="Here is the answer")
    stt_segments = [
        TranscriptSegment(text="How many policies?", confidence=0.9, is_final=True, offset_ms=0, duration_ms=1000)
    ]
    stt = StubSTT(stt_segments)
    tts = StubTTS()
    handler = VoiceCallHandler(
        session_manager=session_manager,
        rag_pipeline=pipeline,
        stt_adapter=stt,
        tts_adapter=tts,
        settings=test_settings,
    )
    session = session_manager.start_session(
        tenant_id=str(tenant_id),
        call_sid="CA456",
        caller_number="+15550001111",
        callee_number="+15550009999",
    )

    async def stream() -> AsyncIterator[bytes]:
        yield b"audio"

    turns = await handler.process_stream(
        session_id=session.id,
        tenant_id=str(tenant_id),
        call_sid=session.twilio_call_sid,
        audio_stream=stream(),
    )
    assert any(isinstance(turn, AssistantTurn) for turn in turns)
    with SessionLocal() as db:
        stored_turns = db.query(CallTurn).filter(CallTurn.session_id == session.id).all()
        speakers = {turn.speaker for turn in stored_turns}
        assert speakers == {"caller", "assistant"}


@pytest.mark.asyncio
async def test_low_confidence_prompts_retry(
    test_settings: Settings,
    session_manager: CallSessionManager,
    tenant_id: uuid.UUID,
):
    test_settings.voice_confidence_threshold = 0.8
    pipeline = StubPipeline(answer="Should not be called")
    stt_segments = [
        TranscriptSegment(text="hello", confidence=0.3, is_final=True, offset_ms=0, duration_ms=1000)
    ]
    stt = StubSTT(stt_segments)
    tts = StubTTS()
    handler = VoiceCallHandler(
        session_manager=session_manager,
        rag_pipeline=pipeline,
        stt_adapter=stt,
        tts_adapter=tts,
        settings=test_settings,
    )
    session = session_manager.start_session(
        tenant_id=str(tenant_id),
        call_sid="CA789",
        caller_number="+15550002222",
        callee_number="+15550003333",
    )

    async def stream() -> AsyncIterator[bytes]:
        yield b"audio"

    turns = await handler.process_stream(
        session_id=session.id,
        tenant_id=str(tenant_id),
        call_sid=session.twilio_call_sid,
        audio_stream=stream(),
    )
    assert pipeline.calls == []
    assert any(turn.text.startswith("I'm sorry") for turn in turns)
