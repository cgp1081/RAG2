from __future__ import annotations

import pytest

from backend.retrieval.models import RetrievalFilters, RetrievalResponse, RetrievedChunk
from backend.retrieval.service import RetrievalService
from backend.retrieval.dependencies import get_retrieval_service


class FakeRetrievalService(RetrievalService):
    def __init__(self, response: RetrievalResponse):
        self._response = response

    async def retrieve(self, *args, **kwargs):  # type: ignore[override]
        return self._response


@pytest.mark.asyncio
async def test_retrieval_endpoint_returns_chunks(app, async_client):
    response_payload = RetrievalResponse(
        chunks=[
            RetrievedChunk(
                chunk_id="chunk-1",
                document_id="doc-1",
                tenant_id="tenant-a",
                score=0.8,
                normalized_score=0.95,
                content="Sample chunk content",
                metadata={"foo": "bar"},
            )
        ],
        applied_filters=RetrievalFilters(source_type=["pdf"]),
        diagnostics={"kept": 1},
    )
    app.dependency_overrides[get_retrieval_service] = lambda: FakeRetrievalService(response_payload)

    response = await async_client.post(
        "/v1/retrieval/query",
        json={"query": "test", "tenant_id": "tenant-a", "filters": {"source_type": ["pdf"]}},
    )

    app.dependency_overrides.pop(get_retrieval_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["chunks"][0]["chunk_id"] == "chunk-1"
    assert body["chunks"][0]["content"] == "Sample chunk content"
    assert body["applied_filters"]["source_type"] == ["pdf"]
    assert body["diagnostics"] == {"kept": 1}


@pytest.mark.asyncio
async def test_retrieval_endpoint_defaults_tenant(app, async_client, test_settings):
    response_payload = RetrievalResponse(chunks=[], applied_filters=None, diagnostics={})
    app.dependency_overrides[get_retrieval_service] = lambda: FakeRetrievalService(response_payload)

    response = await async_client.post(
        "/v1/retrieval/query",
        json={"query": "test"},
    )

    app.dependency_overrides.pop(get_retrieval_service, None)

    assert response.status_code == 200
    assert response.json()["chunks"] == []
