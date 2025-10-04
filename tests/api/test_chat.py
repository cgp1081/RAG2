from __future__ import annotations

import pytest

from backend.rag import get_rag_pipeline
from backend.rag.llm_client import LLMTimeoutError
from backend.rag.pipeline import Citation, RAGResult, TokenUsage
from backend.retrieval.models import RetrievalFilters


class FakePipeline:
    def __init__(self, result: RAGResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[tuple[str, str, RetrievalFilters | None]] = []

    async def generate_answer(self, query: str, tenant_id: str, filters: RetrievalFilters | None = None) -> RAGResult:
        self.calls.append((query, tenant_id, filters))
        if self._error:
            raise self._error
        assert self._result is not None
        return self._result


@pytest.mark.asyncio
async def test_chat_query_returns_answer(app, async_client, test_settings):
    result = RAGResult(
        answer="Final answer with [1]",
        model="stub-model",
        prompt="prompt text",
        prompt_id="prompt-123",
        citations=[
            Citation(
                document_id="doc-1",
                chunk_id="chunk-1",
                source_type="manual",
                title="Employee Handbook",
                snippet="Snippet",
                score=0.9,
                normalized_score=0.95,
            )
        ],
        token_usage=TokenUsage(prompt_tokens=8, completion_tokens=12, total_tokens=20),
        latency_ms=42.5,
    )
    fake_pipeline = FakePipeline(result=result)

    async def override_pipeline():
        return fake_pipeline

    app.dependency_overrides[get_rag_pipeline] = override_pipeline

    response = await async_client.post(
        "/chat/query",
        json={"query": "What policies apply?"},
        headers={"X-Chat-API-Key": test_settings.chat_api_key},
    )

    app.dependency_overrides.pop(get_rag_pipeline, None)

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == result.answer
    assert len(body["citations"]) == 1
    assert body["citations"][0]["document_id"] == "doc-1"
    assert body["token_usage"]["total_tokens"] == 20
    assert body["latency_ms"] == pytest.approx(result.latency_ms)
    assert fake_pipeline.calls[0][1] == test_settings.ingest_default_tenant


@pytest.mark.asyncio
async def test_chat_query_returns_i_dont_know(app, async_client, test_settings):
    result = RAGResult(
        answer="I don't know",
        model="stub-model",
        prompt="prompt text",
        prompt_id="prompt-456",
        citations=[],
        token_usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        latency_ms=5.0,
    )
    fake_pipeline = FakePipeline(result=result)

    async def override_pipeline():
        return fake_pipeline

    app.dependency_overrides[get_rag_pipeline] = override_pipeline

    response = await async_client.post(
        "/chat/query",
        json={"query": "Unknown?", "tenant_id": "custom-tenant"},
        headers={"X-Chat-API-Key": test_settings.chat_api_key},
    )

    app.dependency_overrides.pop(get_rag_pipeline, None)

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "I don't know"
    assert body["citations"] == []
    assert body["token_usage"]["total_tokens"] == 0


@pytest.mark.asyncio
async def test_chat_query_missing_api_key_returns_unauthorised(app, async_client):
    response = await async_client.post(
        "/chat/query",
        json={"query": "Hello"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing X-Chat-API-Key header"


@pytest.mark.asyncio
async def test_chat_query_timeout_returns_504(app, async_client, test_settings):
    fake_pipeline = FakePipeline(error=LLMTimeoutError("Request timed out"))

    async def override_pipeline():
        return fake_pipeline

    app.dependency_overrides[get_rag_pipeline] = override_pipeline

    response = await async_client.post(
        "/chat/query",
        json={"query": "Hello"},
        headers={"X-Chat-API-Key": test_settings.chat_api_key},
    )

    app.dependency_overrides.pop(get_rag_pipeline, None)

    assert response.status_code == 504
    assert "timed out" in response.json()["detail"].lower()
