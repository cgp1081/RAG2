"""Placeholder voice worker utilities."""
from __future__ import annotations

from backend.voice.stt_adapter import TranscriptSegment


async def process_call_turn(session_id: str, segment: TranscriptSegment) -> None:
    """Placeholder coroutine for background processing of call turns."""

    # TODO: Enqueue segments for downstream analytics or supervisor review.
    _ = (session_id, segment)
    return None
