from __future__ import annotations

import json

import httpx
import pytest

from backend.services.embedding_service import EmbeddingService
from backend.services.exceptions import EmbeddingServiceError, EmbeddingTimeoutError


def build_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, base_url="http://test")


@pytest.mark.asyncio
async def test_embedding_service_uses_fallback_model() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/embeddings":
            body = json.loads(request.content)
            calls.append(body["model"])
            if body["model"] == "primary":
                return httpx.Response(503, json={"error": "busy"})
            data = [
                {"embedding": [0.1, 0.2, 0.3], "index": idx}
                for idx, _ in enumerate(body["input"])
            ]
            return httpx.Response(200, json={"data": data})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with build_client(transport) as client:
        service = EmbeddingService(
            client,
            base_url="http://test",
            model="primary",
            fallback_models=["fallback"],
            vector_dim=3,
            timeout_seconds=2.0,
            retry_factory=None,
        )
        vectors = await service.embed(["hello"])

    assert calls.count("primary") >= 1
    assert calls[-1] == "fallback"
    assert vectors == [[0.1, 0.2, 0.3]]


@pytest.mark.asyncio
async def test_embedding_service_dimension_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/embeddings":
            body = json.loads(request.content)
            data = [{"embedding": [0.1, 0.2], "index": 0} for _ in body["input"]]
            return httpx.Response(200, json={"data": data})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with build_client(transport) as client:
        service = EmbeddingService(
            client,
            base_url="http://test",
            model="primary",
            fallback_models=None,
            vector_dim=3,
            timeout_seconds=2.0,
            retry_factory=None,
        )
        with pytest.raises(EmbeddingServiceError):
            await service.embed(["hello"])


@pytest.mark.asyncio
async def test_embedding_service_timeout() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    async with build_client(transport) as client:
        service = EmbeddingService(
            client,
            base_url="http://test",
            model="primary",
            fallback_models=None,
            vector_dim=3,
            timeout_seconds=0.1,
            retry_factory=None,
        )
        with pytest.raises(EmbeddingTimeoutError):
            await service.embed(["hello"])


@pytest.mark.asyncio
async def test_embedding_healthcheck_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(503)
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    async with build_client(transport) as client:
        service = EmbeddingService(
            client,
            base_url="http://test",
            model="primary",
            fallback_models=None,
            vector_dim=3,
            timeout_seconds=2.0,
            retry_factory=None,
        )
        with pytest.raises(EmbeddingServiceError):
            await service.healthcheck()
