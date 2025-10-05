"""Voice call orchestration integrating RAG pipeline, storage, and analytics."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, List, Optional

import structlog
from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.observability import record_voice_call_duration
from backend.db.models import CallRecording, CallSession, CallTurn
from backend.db.session import SessionLocal
from backend.rag.pipeline import RAGPipeline
from backend.voice.storage import (
    CallStorageAdapter,
    NullCallStorageAdapter,
    build_call_storage_adapter,
)
from backend.voice.stt_adapter import DeepgramSTTAdapter
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
class AssistantTurn:
    text: str
    audio: bytes
    confidence: float


class CallSessionManager:
    """Persistence helper for voice call sessions and constituent data."""

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
        metadata: dict | None = None,
    ) -> CallSession:
        session = self._session_factory()
        try:
            db_obj = CallSession(
                tenant_id=uuid.UUID(str(tenant_id)),
                twilio_call_sid=call_sid,
                caller_number=caller_number,
                callee_number=callee_number,
                caller_metadata=metadata or None,
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
            return session.execute(stmt).scalar_one_or_none()

    def update_status(
        self,
        session_id: uuid.UUID,
        *,
        status: str,
        transcript: str | None = None,
        summary: str | None = None,
        confidence: float | None = None,
        escalated: bool | None = None,
        recording_url: str | None = None,
        storage_object_key: str | None = None,
        avg_turn_latency_ms: float | None = None,
        caller_metadata: dict | None = None,
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
            if summary is not None:
                obj.summary = summary
            if confidence is not None:
                obj.confidence = confidence
            if escalated is not None:
                obj.escalated = escalated
            if recording_url is not None:
                obj.recording_url = recording_url
            if storage_object_key is not None:
                obj.storage_object_key = storage_object_key
            if avg_turn_latency_ms is not None:
                obj.avg_turn_latency_ms = avg_turn_latency_ms
            if caller_metadata:
                existing = obj.caller_metadata or {}
                existing.update(caller_metadata)
                obj.caller_metadata = existing
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

    def merge_metadata(self, session_id: uuid.UUID, metadata: dict | None) -> None:
        if not metadata:
            return
        session = self._session_factory()
        try:
            obj = session.get(CallSession, session_id)
            if obj is None:
                return
            existing = obj.caller_metadata or {}
            existing.update(metadata)
            obj.caller_metadata = existing
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
        storage_adapter: CallStorageAdapter | NullCallStorageAdapter,
        settings: Settings,
    ) -> None:
        self._manager = session_manager
        self._pipeline = rag_pipeline
        self._stt = stt_adapter
        self._tts = tts_adapter
        self._storage = storage_adapter
        self._settings = settings
        cfg = settings.voice_config()
        self._voice_config = VoiceConfig(
            twilio_account_sid=cfg.twilio_account_sid,
            twilio_auth_token=cfg.twilio_auth_token,
            stt_api_key=cfg.stt_api_key,
            tts_api_key=cfg.tts_api_key,
            confidence_threshold=cfg.confidence_threshold,
            recordings_path=cfg.recordings_path,
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
        metadata: dict | None = None,
    ) -> tuple[str, uuid.UUID]:
        session = self._manager.start_session(
            tenant_id=tenant_id,
            call_sid=call_sid,
            caller_number=caller_number,
            callee_number=callee_number,
            metadata=metadata,
        )
        response = self._build_twiml(session.id)
        return response, session.id

    def handle_status_callback(
        self,
        *,
        session_id: uuid.UUID,
        status: str,
        error: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        status_map = {
            "ringing": "initiated",
            "in-progress": "running",
            "completed": "completed",
            "failed": "failed",
        }
        mapped = status_map.get(status.lower(), "running")
        ended_at = datetime.now(timezone.utc) if mapped in {"completed", "failed"} else None
        self._manager.update_status(session_id, status=mapped, error=error, ended_at=ended_at)
        if metadata:
            self._manager.merge_metadata(session_id, metadata)

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
        context_logger = self._logger.bind(call_session_id=str(session_id), tenant_id=tenant_id)
        context_logger.info("voice.stream.start")
        assistant_turns: list[AssistantTurn] = []
        transcript_parts: list[str] = []
        confidence_scores: list[float] = []
        latencies_ms: list[float] = []

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
                caller_start = datetime.now(timezone.utc)
                self._manager.append_turn(
                    session_id,
                    speaker="caller",
                    text=text,
                    confidence=segment.confidence,
                    started_at=caller_start,
                    ended_at=datetime.now(timezone.utc),
                )
                caller_end = datetime.now(timezone.utc)

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
                response_time = datetime.now(timezone.utc)
                latency_ms = (response_time - caller_end).total_seconds() * 1000
                latencies_ms.append(latency_ms)
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
            avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else None
            transcript_text = "\n".join(transcript_parts)
            summary = (transcript_text[:200] + "...") if len(transcript_text) > 200 else transcript_text

            escalated = aggregate_confidence < self._voice_config.confidence_threshold
            for turn in assistant_turns:
                if turn.text.strip().lower() in {"i don't know", "i do not know"}:
                    escalated = True
                    break
            # TODO: consider tenant-specific escalation rules (keywords, sentiment, manual override)

            storage_key = ""
            presigned_url = ""
            call_session = self._manager.get_session(session_id)
            recordings_dir = Path(self._voice_config.recordings_path)
            if call_session and recordings_dir.exists():
                candidate = _locate_recording(recordings_dir, session_id)
                if candidate:
                    storage_key = self._storage.upload(call_session, candidate)
                    if storage_key:
                        presigned_url = self._storage.presign(storage_key)

            self._manager.update_status(
                session_id,
                status="completed",
                transcript=transcript_text,
                summary=summary,
                confidence=aggregate_confidence,
                escalated=escalated,
                recording_url=presigned_url or None,
                storage_object_key=storage_key or None,
                avg_turn_latency_ms=avg_latency,
                caller_metadata={"handle_seconds": duration},
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
        for _ in range(retries + 1):
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
            return (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                "<Response><Say>Connecting you to the assistant.</Say></Response>"
            )

        response = VoiceResponse()
        start: Start = response.start()
        start.stream(url=f"/voice/stream/{session_id}")
        response.say("Connecting you to the assistant.")
        return str(response)


def _locate_recording(recordings_dir: Path, session_id: uuid.UUID) -> Path | None:
    for ext in (".wav", ".mp3", ".ogg"):
        candidate = recordings_dir / f"{session_id}{ext}"
        if candidate.exists():
            return candidate
    return None


def build_default_voice_handler(settings: Settings, pipeline: RAGPipeline) -> VoiceCallHandler:
    manager = CallSessionManager()
    stt_adapter = DeepgramSTTAdapter(settings.voice_stt_api_key)
    tts_adapter = TTSAdapter(settings.voice_tts_api_key)
    storage_adapter = build_call_storage_adapter(settings)
    return VoiceCallHandler(
        session_manager=manager,
        rag_pipeline=pipeline,
        stt_adapter=stt_adapter,
        tts_adapter=tts_adapter,
        storage_adapter=storage_adapter,
        settings=settings,
    )


__all__ = [
    "AssistantTurn",
    "CallSessionManager",
    "VoiceCallHandler",
    "build_default_voice_handler",
]
