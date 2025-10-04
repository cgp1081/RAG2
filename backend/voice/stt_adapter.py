"""Speech-to-text adapter for streaming call audio."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import structlog

try:  # pragma: no cover - optional dependency
    from deepgram import Deepgram
except Exception:  # pragma: no cover - deepgram SDK optional
    Deepgram = None  # type: ignore


logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class TranscriptSegment:
    text: str
    confidence: float
    is_final: bool
    offset_ms: int
    duration_ms: int


class DeepgramSTTAdapter:
    """Stream audio bytes to Deepgram (or stub fallback when unavailable)."""

    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key
        self._client: Optional[Deepgram] = None
        if api_key and Deepgram is not None:
            try:  # pragma: no cover - networked dependency
                self._client = Deepgram(api_key)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("voice.stt.init_failed", error=str(exc))
                self._client = None
        elif api_key and Deepgram is None:
            logger.warning("voice.stt.deepgram_missing")

    async def stream_transcript(
        self,
        stream: AsyncIterator[bytes],
        *,
        language: str = "en-US",
    ) -> AsyncIterator[TranscriptSegment]:
        if self._client is None or not self._api_key:  # Fallback stub path
            collected = bytearray()
            async for chunk in stream:
                collected.extend(chunk)
            text = self._heuristic_transcript(bytes(collected))
            yield TranscriptSegment(
                text=text,
                confidence=0.5,
                is_final=True,
                offset_ms=0,
                duration_ms=0,
            )
            return

        buffer = bytearray()
        async for chunk in stream:
            buffer.extend(chunk)

        if not buffer:
            return

        try:  # pragma: no cover - relies on external API
            response = await self._client.transcription.prerecorded(
                {
                    "buffer": bytes(buffer),
                    "mimetype": "audio/wav",
                },
                {
                    "language": language,
                    "punctuate": True,
                    "utterances": True,
                },
            )
        except Exception as exc:  # pragma: no cover - network failure fallback
            logger.warning("voice.stt.deepgram_error", error=str(exc))
            text = self._heuristic_transcript(bytes(buffer))
            yield TranscriptSegment(text=text, confidence=0.4, is_final=True, offset_ms=0, duration_ms=0)
            return

        utterances = (
            response.get("results", {})
            .get("utterances", [])
        ) if isinstance(response, dict) else []
        if not utterances:
            text = self._heuristic_transcript(bytes(buffer))
            yield TranscriptSegment(text=text, confidence=0.4, is_final=True, offset_ms=0, duration_ms=0)
            return

        for utterance in utterances:
            text = utterance.get("transcript", "")
            confidence = float(utterance.get("confidence", 0.0))
            start = int(utterance.get("start", 0) * 1000)
            end = int(utterance.get("end", 0) * 1000)
            yield TranscriptSegment(
                text=text,
                confidence=confidence,
                is_final=True,
                offset_ms=start,
                duration_ms=end - start,
            )

    @staticmethod
    def _heuristic_transcript(audio: bytes) -> str:
        if not audio:
            return ""
        try:
            decoded = audio.decode("utf-8")
            return decoded.strip() or "(audio)"
        except UnicodeDecodeError:
            snippet = base64.b64encode(audio[:32]).decode("ascii")
            return f"(audio:{snippet}...)"
