"""Embedding service abstraction for Ollama-compatible APIs."""
from __future__ import annotations

from collections.abc import Callable, Sequence

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from backend.app.config import Settings
from backend.app.logging import get_logger
from backend.services.exceptions import (
    EmbeddingRetryableError,
    EmbeddingServiceError,
    EmbeddingTimeoutError,
)

RetryFactory = Callable[[], AsyncRetrying]


class EmbeddingService:
    """Client for obtaining embeddings with retries and fallbacks."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        model: str,
        fallback_models: Sequence[str] | None,
        vector_dim: int,
        timeout_seconds: float,
        retry_factory: RetryFactory | None = None,
    ) -> None:
        self._client = client
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.fallback_models = list(fallback_models or [])
        self.vector_dim = vector_dim
        self.timeout_seconds = timeout_seconds
        self._retry_factory = retry_factory or self._default_retry_factory
        self._logger = get_logger(__name__)

    @staticmethod
    def _default_retry_factory() -> AsyncRetrying:
        return AsyncRetrying(
            wait=wait_exponential_jitter(initial=0.5, max=5.0),
            stop=stop_after_attempt(3),
            retry=retry_if_exception_type(
                (EmbeddingRetryableError, EmbeddingTimeoutError)
            ),
            reraise=True,
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return embeddings for the provided texts, using fallbacks when needed."""

        if not texts:
            return []

        models_to_try = [self.model, *self.fallback_models]
        last_error: Exception | None = None

        for model_name in models_to_try:
            try:
                embeddings = await self._embed_with_retry(model_name, texts)
            except EmbeddingRetryableError as exc:
                last_error = exc
                self._logger.warning(
                    "embedding.retryable",
                    model=model_name,
                    error=str(exc),
                )
                continue
            except EmbeddingServiceError as exc:
                if isinstance(exc, EmbeddingTimeoutError):
                    raise exc
                last_error = exc
                self._logger.error(
                    "embedding.failure",
                    model=model_name,
                    error=str(exc),
                )
                continue
            else:
                return embeddings

        message = (
            "Failed to generate embeddings after trying models: "
            f"{models_to_try}; last error: {last_error}"
        )
        raise EmbeddingServiceError(message) from last_error

    async def _embed_with_retry(self, model_name: str, texts: Sequence[str]) -> list[list[float]]:
        try:
            async for attempt in self._retry_factory():
                with attempt:
                    return await self._request_embeddings(model_name, texts)
        except RetryError as exc:
            last_exc = exc.last_attempt.exception()
            if isinstance(last_exc, EmbeddingTimeoutError):
                raise last_exc
            raise EmbeddingRetryableError(
                f"Embedding retries exhausted for model {model_name}: {exc}"
            ) from exc

    async def _request_embeddings(self, model_name: str, texts: Sequence[str]) -> list[list[float]]:
        payload = {"model": model_name, "input": list(texts)}
        url = f"{self.base_url}/api/embeddings"
        try:
            response = await self._client.post(
                url,
                json=payload,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise EmbeddingTimeoutError(
                f"Embedding request timed out for model {model_name}"
            ) from exc
        except httpx.RequestError as exc:
            raise EmbeddingRetryableError(
                f"Request error for model {model_name}: {exc}"
            ) from exc

        if response.status_code >= 500 or response.status_code in {408, 429}:
            message = (
                "Embedding service temporary failure "
                f"({response.status_code}) for model {model_name}"
            )
            raise EmbeddingRetryableError(message)
        if response.status_code >= 400:
            message = (
                "Embedding service returned "
                f"{response.status_code} for model {model_name}: {response.text}"
            )
            raise EmbeddingServiceError(message)

        data = response.json()
        items = data.get("data")
        if not isinstance(items, list) or not items:
            raise EmbeddingServiceError("Embedding response missing data field")

        embeddings = []
        for item in items:
            vector = item.get("embedding")
            if not isinstance(vector, list) or len(vector) != self.vector_dim:
                message = (
                    "Embedding dimension mismatch for model "
                    f"{model_name}: expected {self.vector_dim}"
                )
                raise EmbeddingServiceError(message)
            embeddings.append([float(v) for v in vector])

        if len(embeddings) != len(texts):
            raise EmbeddingServiceError(
                f"Embedding count mismatch: expected {len(texts)}, got {len(embeddings)}"
            )

        self._logger.info(
            "embedding.success", model=model_name, count=len(embeddings)
        )
        return embeddings

    async def healthcheck(self) -> None:
        url = f"{self.base_url}/api/tags"
        try:
            response = await self._client.get(url, timeout=self.timeout_seconds)
        except httpx.TimeoutException as exc:
            raise EmbeddingTimeoutError("Embedding healthcheck timed out") from exc
        except httpx.RequestError as exc:
            raise EmbeddingRetryableError(f"Healthcheck request error: {exc}") from exc

        if response.status_code != 200:
            raise EmbeddingServiceError(
                f"Embedding service unhealthy: status {response.status_code}"
            )


def build_embedding_service(settings: Settings, client: httpx.AsyncClient) -> EmbeddingService:
    """Factory for a configured EmbeddingService instance."""

    return EmbeddingService(
        client,
        base_url=str(settings.ollama_base_url),
        model=settings.embedding_model,
        fallback_models=settings.embedding_fallback_models,
        vector_dim=settings.vector_dim,
        timeout_seconds=settings.vector_timeout_seconds,
    )
