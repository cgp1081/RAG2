"""Voice call orchestration integrating RAG pipeline and adapters."""
from __future__ import annotations

import asyncio
import base64
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, List, Optional

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.observability import record_voice_call_duration
from backend.db.models import CallRecording, CallSession, CallTurn
from backend.db.session import SessionLocal
from backend.rag.pipeline import RAGPipeline
from backend.voice.stt_adapter import DeepgramSTTAdapter, TranscriptSegment
from backend.voice.tts_adapter import TTSAdapter
from backend.voice.worker import process_call_turn

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class VoiceConfig:
    twilio_account_sid: str | None
    twilio_auth_token: str | None
    stt_api_key: str | None
    tts_api_key: str | None
    confidence_threshold: float
    recordings_path: str
    stream_timeout_seconds: float


@dataclass(slots=True)
class CallContext:
    session_id: uuid.UUID
    tenant_id: str
    call_sid: str
    caller_number: str | None
    callee_number: str | None


@dataclass(slots=True)
class AssistantTurn:
    text: str
    audio: bytes
    confidence: float


class CallSessionManager:
    """Persistence helper for voice call sessions and turns."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory
        self._logger = logger.bind(component="call_session_manager")

    def start_session(
        self,
        *,
        tenant_id: str,
        call_sid: str,
        caller_number: str | None,
        callee_number: str | None,
    ) -> CallSession:
        session = self._session_factory()
        try:
        db_obj = CallSession(
            tenant_id=uuid.UUID(str(tenant_id)),
            twilio_call_sid=call_sid,
            caller_number=caller_number,
            callee_number=callee_number,
        )
            session.add(db_obj)
            session.commit()
            session.refresh(db_obj)
            self._logger.info(
                "voice.session.started",
                call_session_id=str(db_obj.id),
                call_sid=call_sid,
                tenant_id=tenant_id,
            )
            return db_obj
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_session(self, session_id: uuid.UUID) -> Optional[CallSession]:
        with self._session_factory() as session:
            return session.get(CallSession, session_id)

    def get_session_by_sid(self, call_sid: str) -> Optional[CallSession]:
        with self._session_factory() as session:
            stmt = select(CallSession).where(CallSession.twilio_call_sid == call_sid)
            result = session.execute(stmt).scalar_one_or_none()
            return result

    def update_status(
        self,
        session_id: uuid.UUID,
        *,
        status: str,
        transcript: str | None = None,
        confidence: float | None = None,
        error: str | None = None,
        ended_at: Optional[datetime] = None,
    ) -> None:
        session = self._session_factory()
        try:
            obj = session.get(CallSession, session_id)
            if obj is None:
                self._logger.warning("voice.session.missing", call_session_id=str(session_id))
                return
            obj.status = status
            if transcript is not None:
                obj.transcript = transcript
            if confidence is not None:
                obj.confidence = confidence
            if error:
                obj.error = error
            if ended_at is not None:
                obj.ended_at = ended_at
            obj.updated_at = datetime.now(timezone.utc)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def append_turn(
        self,
        session_id: uuid.UUID,
        *,
        speaker: str,
        text: str,
        confidence: float | None,
        started_at: datetime | None,
        ended_at: datetime | None,
    ) -> CallTurn:
        session = self._session_factory()
        try:
            next_sequence = session.execute(
                select(func.coalesce(func.max(CallTurn.sequence), 0)).where(
                    CallTurn.session_id == session_id
                )
            ).scalar_one()
            turn = CallTurn(
                session_id=session_id,
                sequence=next_sequence + 1,
                speaker=speaker,
                text=text,
                confidence=confidence,
                started_at=started_at,
                ended_at=ended_at,
            )
            session.add(turn)
            session.commit()
            session.refresh(turn)
            return turn
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save_recording(
        self,
        session_id: uuid.UUID,
        *,
        media_uri: str | None,
        content_type: str | None,
        duration_seconds: float | None,
        storage_path: str | None,
    ) -> CallRecording:
        session = self._session_factory()
        try:
            recording = CallRecording(
                session_id=session_id,
                media_uri=media_uri,
                content_type=content_type,
                duration_seconds=duration_seconds,
                storage_path=storage_path,
            )
            session.add(recording)
            session.commit()
            session.refresh(recording)
            return recording
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class VoiceCallHandler:
    """Coordinate voice call flow with RAG pipeline and adapters."""

    def __init__(
        self,
        *,
        session_manager: CallSessionManager,
        rag_pipeline: RAGPipeline,
        stt_adapter: DeepgramSTTAdapter,
        tts_adapter: TTSAdapter,
        settings: Settings,
    ) -> None:
        self._manager = session_manager
        self._pipeline = rag_pipeline
        self._stt = stt_adapter
        self._tts = tts_adapter
        self._settings = settings
        cfg = settings.voice_config()
        self._voice_config = VoiceConfig(
            twilio_account_sid=cfg.twilio_account_sid,
            twilio_auth_token=cfg.twilio_auth_token,
            stt_api_key=cfg.stt_api_key,
            tts_api_key=cfg.tts_api_key,
            confidence_threshold=cfg.confidence_threshold,
            recordings_path=str(cfg.recordings_path),
            stream_timeout_seconds=cfg.stream_timeout_seconds,
        )
        self._logger = logger.bind(component="voice_handler")

    def handle_inbound_call(
        self,
        *,
        call_sid: str,
        tenant_id: str,
        caller_number: str | None,
        callee_number: str | None,
    ) -> tuple[str, uuid.UUID]:
        session = self._manager.start_session(
            tenant_id=tenant_id,
            call_sid=call_sid,
            caller_number=caller_number,
            callee_number=callee_number,
        )
        response = self._build_twiml(session.id)
        return response, session.id

    def handle_status_callback(self, *, session_id: uuid.UUID, status: str, error: str | None = None) -> None:
        status_map = {
            "ringing": "initiated",
            "in-progress": "running",
            "completed": "completed",
            "failed": "failed",
        }
        mapped = status_map.get(status.lower(), "running")
        ended_at = datetime.now(timezone.utc) if mapped in {"completed", "failed"} else None
        self._manager.update_status(session_id, status=mapped, error=error, ended_at=ended_at)

    def get_session(self, session_id: uuid.UUID) -> Optional[CallSession]:
        return self._manager.get_session(session_id)

    async def process_stream(
        self,
        session_id: uuid.UUID,
        tenant_id: str,
        call_sid: str,
        audio_stream: AsyncIterator[bytes],
    ) -> List[AssistantTurn]:
        start_time = datetime.now(timezone.utc)
        context_logger = self._logger.bind(call_session_id=str(session_id), call_sid=call_sid, tenant_id=tenant_id)
        context_logger.info("voice.stream.start")
        self._manager.update_status(session_id, status="running")
        assistant_turns: list[AssistantTurn] = []
        transcript_parts: list[str] = []
        confidence_scores: list[float] = []

        try:
            async for segment in self._stt.stream_transcript(audio_stream):
                asyncio.create_task(process_call_turn(str(session_id), segment))
                if not segment.is_final:
                    continue
                text = segment.text.strip()
                if not text:
                    continue
                transcript_parts.append(text)
                confidence_scores.append(segment.confidence)
                self._manager.append_turn(
                    session_id,
                    speaker="caller",
                    text=text,
                    confidence=segment.confidence,
                    started_at=start_time,
                    ended_at=datetime.now(timezone.utc),
                )

                if segment.confidence < self._voice_config.confidence_threshold:
                    fallback = "I'm sorry, could you repeat that?"
                    audio = await self._safely_synthesize(fallback)
                    self._manager.append_turn(
                        session_id,
                        speaker="assistant",
                        text=fallback,
                        confidence=1.0,
                        started_at=datetime.now(timezone.utc),
                        ended_at=None,
                    )
                    assistant_turns.append(
                        AssistantTurn(text=fallback, audio=audio, confidence=segment.confidence)
                    )
                    context_logger.info("voice.segment.low_confidence", confidence=segment.confidence)
                    continue

                answer = await self._run_pipeline(text, tenant_id)
                audio = await self._safely_synthesize(answer)
                self._manager.append_turn(
                    session_id,
                    speaker="assistant",
                    text=answer,
                    confidence=segment.confidence,
                    started_at=datetime.now(timezone.utc),
                    ended_at=None,
                )
                assistant_turns.append(
                    AssistantTurn(text=answer, audio=audio, confidence=segment.confidence)
                )
                context_logger.info("voice.segment.responded", response=answer)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            aggregate_confidence = (
                sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
            )
            self._manager.update_status(
                session_id,
                status="completed",
                transcript="\n".join(transcript_parts),
                confidence=aggregate_confidence,
                ended_at=datetime.now(timezone.utc),
            )
            record_voice_call_duration(
                tenant_id=tenant_id,
                outcome="completed",
                duration_seconds=duration,
            )
            context_logger.info("voice.stream.completed", duration_seconds=duration)
            return assistant_turns
        except Exception as exc:
            context_logger.error("voice.stream.failed", error=str(exc))
            self._manager.update_status(
                session_id,
                status="failed",
                error=str(exc),
                ended_at=datetime.now(timezone.utc),
            )
            record_voice_call_duration(
                tenant_id=tenant_id,
                outcome="failed",
                duration_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
            )
            raise

    async def _run_pipeline(self, text: str, tenant_id: str) -> str:
        async def _attempt() -> str:
            result = await self._pipeline.generate_answer(query=text, tenant_id=tenant_id)
            return result.answer

        return await self._with_retries(_attempt)

    async def _safely_synthesize(self, text: str) -> bytes:
        async def _attempt() -> bytes:
            return await self._tts.synthesize(text)

        return await self._with_retries(_attempt)

    async def _with_retries(self, func, retries: int = 2):
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return await func()
            except Exception as exc:  # pragma: no cover - network fallback
                last_exc = exc
                await asyncio.sleep(0.2)
        if last_exc:
            self._logger.error("voice.retry.exhausted", error=str(last_exc))
            raise last_exc
        raise RuntimeError("voice retry exhausted")

    def _build_twiml(self, session_id: uuid.UUID) -> str:
        try:
            from twilio.twiml.voice_response import Start, VoiceResponse
        except Exception:  # pragma: no cover - twilio optional dependency
            placeholder = (
                f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                f"<Response><Say>Connecting you to the assistant.</Say></Response>"
            )
            return placeholder

        response = VoiceResponse()
        start: Start = response.start()
        start.stream(url=f"/voice/stream/{session_id}")
        response.say("Connecting you to the assistant.")
        return str(response)
