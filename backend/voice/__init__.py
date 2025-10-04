"""Voice adapter factory helpers."""
from __future__ import annotations

from typing import Optional

from backend.app.config import Settings

from .stt_adapter import DeepgramSTTAdapter, TranscriptSegment
from .tts_adapter import TTSAdapter


def build_stt_adapter(settings: Settings) -> DeepgramSTTAdapter:
    return DeepgramSTTAdapter(settings.voice_stt_api_key)


def build_tts_adapter(settings: Settings) -> TTSAdapter:
    return TTSAdapter(settings.voice_tts_api_key)


__all__ = [
    "DeepgramSTTAdapter",
    "TranscriptSegment",
    "TTSAdapter",
    "build_stt_adapter",
    "build_tts_adapter",
]
