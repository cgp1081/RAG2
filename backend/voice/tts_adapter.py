"""Text-to-speech adapter for assistant responses."""
from __future__ import annotations

from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class TTSAdapter:
    """Produce audio payloads for assistant responses."""

    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key

    async def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        if not text:
            return b""
        if not self._api_key:
            logger.info("voice.tts.fallback", voice=voice)
            return b""
        try:  # pragma: no cover - network stub
            # Placeholder for real vendor call (e.g., ElevenLabs, AWS Polly)
            return text.encode("utf-8")
        except Exception as exc:  # pragma: no cover - fallback
            logger.warning("voice.tts.error", error=str(exc))
            return b""
