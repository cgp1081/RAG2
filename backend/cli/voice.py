"""CLI helpers for voice simulation."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

import aiofiles
import httpx
import typer

from backend.app.config import get_settings
from backend.app.logging import get_logger
from backend.db.session import SessionLocal
from backend.rag.llm_client import build_llm_client
from backend.rag.pipeline import RAGPipeline
from backend.rag.prompts import PromptBuilder
from backend.retrieval.service import RetrievalService
from backend.services import build_embedding_service, build_vector_store
from backend.voice import build_stt_adapter, build_tts_adapter
from backend.voice.call_handler import CallSessionManager, VoiceCallHandler
from backend.voice.storage import build_call_storage_adapter

logger = get_logger(__name__)


async def _simulate_voice_call(
    *,
    audio_path: Path,
    tenant: str,
    phone_number: str,
) -> None:
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    settings = get_settings()
    vector_store = build_vector_store(settings)

    async def audio_stream() -> AsyncIterator[bytes]:
        async with aiofiles.open(audio_path, "rb") as file_handle:
            while True:
                chunk = await file_handle.read(4096)
                if not chunk:
                    break
                yield chunk

    try:
        async with httpx.AsyncClient(timeout=settings.vector_timeout_seconds) as embed_client:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as llm_http:
                embedding_service = build_embedding_service(settings, embed_client)
                retrieval_service = RetrievalService(
                    embedding_service=embedding_service,
                    vector_store=vector_store,
                    settings=settings,
                )
                llm_client = build_llm_client(settings, llm_http)
                pipeline = RAGPipeline(
                    retrieval_service=retrieval_service,
                    llm_client=llm_client,
                    prompt_builder=PromptBuilder(),
                    settings=settings,
                )
                manager = CallSessionManager(SessionLocal)
                stt_adapter = build_stt_adapter(settings)
                tts_adapter = build_tts_adapter(settings)
                handler = VoiceCallHandler(
                    session_manager=manager,
                    rag_pipeline=pipeline,
                    stt_adapter=stt_adapter,
                    tts_adapter=tts_adapter,
                    storage_adapter=build_call_storage_adapter(settings),
                    settings=settings,
                )

                session = manager.start_session(
                    tenant_id=tenant,
                    call_sid=f"SIM-{uuid.uuid4()}",
                    caller_number=phone_number,
                    callee_number="simulated",
                )
                turns = await handler.process_stream(
                    session_id=session.id,
                    tenant_id=tenant,
                    call_sid=session.twilio_call_sid,
                    audio_stream=audio_stream(),
                )
    finally:
        await vector_store.close()

    if not turns:
        typer.echo("No assistant response generated.")
        return

    typer.echo("Assistant Responses:")
    for turn in turns:
        typer.echo(f"- {turn.text} (confidence={turn.confidence:.2f})")


def voice_simulate(  # pragma: no cover - Typer entry point
    audio: Path = typer.Option(..., exists=True, readable=True, path_type=Path),
    tenant: Optional[str] = typer.Option(None, "--tenant", help="Tenant UUID to simulate."),
    phone: str = typer.Option("+15551234567", "--phone", help="Caller number"),
) -> None:
    settings = get_settings()
    tenant_id = tenant or settings.ingest_default_tenant
    try:
        uuid.UUID(str(tenant_id))
    except ValueError as exc:
        raise typer.BadParameter("tenant must be a UUID") from exc
    asyncio.run(_simulate_voice_call(audio_path=audio, tenant=tenant_id, phone_number=phone))


__all__ = ["voice_simulate"]
