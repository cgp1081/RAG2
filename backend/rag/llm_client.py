"""Async client for LLM completion endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from backend.app.config import Settings


class LLMClientError(RuntimeError):
    """Raised when the LLM service responds with an error."""


class LLMTimeoutError(LLMClientError):
    """Raised when the LLM service request times out."""


@dataclass(slots=True)
class LLMResult:
    """Container for LLM responses and token accounting."""

    text: str
    model: str
    token_usage: dict[str, int]


class LLMClient:
    """Lightweight wrapper around an OpenAI-compatible chat completion API."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        model: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout_seconds

    async def generate(self, prompt: str) -> LLMResult:
        """Send a chat completion request and return the parsed result."""

        url = f"{self._base_url}/v1/chat/completions"
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self._max_tokens,
            "temperature": 0.0,
            "stream": False,
        }

        try:
            response = await self._client.post(url, json=payload, timeout=self._timeout)
        except httpx.TimeoutException as exc:  # pragma: no cover - covered via unit fakes
            raise LLMTimeoutError("LLM request timed out") from exc
        except httpx.HTTPError as exc:  # pragma: no cover - network errors handled by callers
            raise LLMClientError(f"LLM request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMClientError(
                f"LLM request failed with status {response.status_code}: {response.text}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMClientError("LLM response was not valid JSON") from exc

        choices = data.get("choices") or []
        content = ""
        if choices:
            first_choice = choices[0] or {}
            message = first_choice.get("message") or {}
            content = (message.get("content") or first_choice.get("text") or "").strip()

        usage_raw: dict[str, Any] = data.get("usage") or {}
        token_usage = {
            "prompt_tokens": int(usage_raw.get("prompt_tokens") or 0),
            "completion_tokens": int(usage_raw.get("completion_tokens") or 0),
            "total_tokens": int(usage_raw.get("total_tokens") or 0),
        }

        model_name = str(data.get("model") or self._model)

        return LLMResult(text=content, model=model_name, token_usage=token_usage)


def build_llm_client(settings: Settings, client: httpx.AsyncClient) -> LLMClient:
    """Factory that initialises ``LLMClient`` from application settings."""

    return LLMClient(
        client=client,
        base_url=str(settings.llm_base_url),
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
    )


__all__ = [
    "LLMClient",
    "LLMClientError",
    "LLMTimeoutError",
    "LLMResult",
    "build_llm_client",
]
