from __future__ import annotations

import pytest

from backend.app.config import Settings
from backend.retrieval.models import RetrievalFilters
from backend.retrieval.service import RetrievalService
from backend.services.vector_store import VectorSearchResult


class FakeEmbeddingService:
    async def embed(self, texts):
        self.last_texts = texts
        return [[1.0, 1.0, 1.0]]


class RecordingVectorStore:
    def __init__(self, results):
        self._results = results
        self.calls: list[dict[str, object]] = []

    async def search_with_filters(self, *, tenant_id, embedding, top_k, filters):
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "embedding": embedding,
                "top_k": top_k,
                "filters": filters,
            }
        )
        return self._results[: top_k or len(self._results)]

    async def close(self):  # pragma: no cover - compatibility hook
        return None


@pytest.mark.asyncio
async def test_retrieve_filters_by_metadata():
    settings = Settings(retrieval_diagnostics=True)
    embedding_service = FakeEmbeddingService()
    vector_results = [
        VectorSearchResult(
            id="chunk-1",
            score=0.9,
            payload={
                "content": "Employee handbook section",
                "document_id": "doc-1",
                "tenant_id": "acme",
                "visibility_scope": "employee",
                "source_type": "pdf",
            },
        ),
        VectorSearchResult(
            id="chunk-2",
            score=0.6,
            payload={
                "content": "Public FAQ entry",
                "document_id": "doc-2",
                "tenant_id": "acme",
                "visibility_scope": "public",
                "source_type": "pdf",
            },
        ),
    ]
    vector_store = RecordingVectorStore(vector_results)
    service = RetrievalService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        settings=settings,
    )

    filters = RetrievalFilters(source_type=["pdf"], visibility_scope="employee")
    response = await service.retrieve(
        query="What is the holiday policy?",
        tenant_id="acme",
        filters=filters,
    )

    assert vector_store.calls[0]["filters"] == {
        "source_type": ["pdf"],
        "visibility_scope": "employee",
    }
    assert len(response.chunks) == 1
    assert response.chunks[0].document_id == "doc-1"
    assert response.chunks[0].normalized_score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_retrieve_applies_score_floor_drops_all():
    settings = Settings(retrieval_diagnostics=True, retrieval_score_floor=1.05)
    embedding_service = FakeEmbeddingService()
    vector_results = [
        VectorSearchResult(
            id="chunk-1",
            score=0.4,
            payload={
                "content": "Low relevance",
                "document_id": "doc-1",
                "tenant_id": "acme",
            },
        )
    ]
    vector_store = RecordingVectorStore(vector_results)
    service = RetrievalService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        settings=settings,
    )

    response = await service.retrieve(
        query="irrelevant",
        tenant_id="acme",
    )

    assert response.chunks == []
    assert response.diagnostics["dropped_below_floor"] == 1


@pytest.mark.asyncio
async def test_retrieve_respects_provided_top_k():
    settings = Settings(retrieval_diagnostics=False)
    embedding_service = FakeEmbeddingService()
    vector_results = [
        VectorSearchResult(id=f"chunk-{i}", score=0.9 - i * 0.05, payload={"document_id": f"doc-{i}"})
        for i in range(5)
    ]
    vector_store = RecordingVectorStore(vector_results)
    service = RetrievalService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        settings=settings,
    )

    await service.retrieve(
        query="policy",
        tenant_id="acme",
        top_k=2,
    )

    assert vector_store.calls[0]["top_k"] == 2


@pytest.mark.asyncio
async def test_retrieve_normalizes_scores_and_orders():
    settings = Settings(retrieval_diagnostics=False, retrieval_score_floor=0.0)
    embedding_service = FakeEmbeddingService()
    vector_results = [
        VectorSearchResult(
            id="chunk-high",
            score=0.8,
            payload={"content": "High", "document_id": "doc-1"},
        ),
        VectorSearchResult(
            id="chunk-mid",
            score=0.5,
            payload={"content": "Mid", "document_id": "doc-2"},
        ),
        VectorSearchResult(
            id="chunk-low",
            score=0.3,
            payload={"content": "Low", "document_id": "doc-3"},
        ),
    ]
    vector_store = RecordingVectorStore(vector_results)
    service = RetrievalService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        settings=settings,
    )

    response = await service.retrieve(
        query="policy",
        tenant_id="acme",
    )

    assert [chunk.chunk_id for chunk in response.chunks] == ["chunk-high", "chunk-mid", "chunk-low"]
    assert all(0.0 <= chunk.normalized_score <= 1.0 for chunk in response.chunks)
    assert response.chunks[0].normalized_score > response.chunks[-1].normalized_score
