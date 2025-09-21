from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Sequence

import httpx
import pytest
from qdrant_client.http.exceptions import UnexpectedResponse

from backend.app.config import Settings
from backend.services.exceptions import VectorCollectionError
from backend.services.vector_store import (
    VectorPayload,
    VectorSearchResult,
    VectorStoreClient,
    build_vector_store,
)


class FakeAsyncQdrantClient:
    """Minimal async client for unit testing VectorStoreClient."""

    def __init__(self, vector_dim: int) -> None:
        self.vector_dim = vector_dim
        self.collections: dict[str, SimpleNamespace] = {}
        self.points: dict[str, list[dict[str, Any]]] = {}

    async def get_collection(self, name: str, timeout: float | None = None) -> Any:
        if name not in self.collections:
            raise UnexpectedResponse(404, "Not Found", b"", httpx.Headers())
        return self.collections[name]

    async def create_collection(
        self,
        name: str,
        *,
        vectors_config,
        timeout: float | None = None,
    ) -> None:
        self.collections[name] = SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=SimpleNamespace(size=vectors_config.size)
                )
            )
        )

    async def upsert(
        self,
        *,
        collection_name: str,
        points: Sequence[dict[str, Any]],
        wait: bool,
        timeout: float | None = None,
    ) -> None:
        self.points.setdefault(collection_name, []).extend(points)

    async def search(
        self,
        *,
        collection_name: str,
        query_vector: Sequence[float],
        limit: int,
        filter: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> list[Any]:
        if collection_name not in self.points:
            return []
        stored = self.points[collection_name]
        results = []
        for point in stored[:limit]:
            results.append(
                SimpleNamespace(id=point["id"], score=1.0, payload=point["payload"])
            )
        return results

    async def get_collections(self, timeout: float | None = None) -> list[str]:
        return list(self.collections.keys())


@pytest.mark.asyncio
async def test_vector_store_creates_and_upserts() -> None:
    client = FakeAsyncQdrantClient(vector_dim=3)
    store = VectorStoreClient(client, collection_prefix="tenant", vector_dim=3)

    await store.ensure_collection("alpha")
    payload: VectorPayload = {
        "id": "doc-1",
        "embedding": [0.1, 0.2, 0.3],
        "metadata": {"source": "test"},
    }
    await store.upsert_embeddings("alpha", [payload])

    results = await store.search("alpha", [0.1, 0.2, 0.3])
    assert results == [VectorSearchResult(id="doc-1", score=1.0, metadata={"source": "test"})]


@pytest.mark.asyncio
async def test_vector_store_collection_dimension_mismatch() -> None:
    client = FakeAsyncQdrantClient(vector_dim=4)
    store = VectorStoreClient(client, collection_prefix="tenant", vector_dim=3)

    # Pre-create the collection with incorrect dimension.
    await client.create_collection("tenant_alpha", vectors_config=SimpleNamespace(size=4))

    with pytest.raises(VectorCollectionError):
        await store.ensure_collection("alpha")


@pytest.mark.asyncio
async def test_vector_store_healthcheck_success() -> None:
    client = FakeAsyncQdrantClient(vector_dim=3)
    store = VectorStoreClient(client, collection_prefix="tenant", vector_dim=3)

    await store.healthcheck()


@pytest.mark.asyncio
async def test_vector_store_integration_roundtrip() -> None:
    qdrant_url = os.getenv("QDRANT_URL")
    if not qdrant_url:
        pytest.skip("QDRANT_URL not configured; skipping integration test")

    settings = Settings(
        qdrant_url=qdrant_url,
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
        vector_timeout_seconds=5.0,
        vector_dim=3,
    )

    store = build_vector_store(settings)
    try:
        await store.healthcheck()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Qdrant unavailable: {exc}")

    tenant_id = "test_integration"
    await store.ensure_collection(tenant_id)
    payload: VectorPayload = {
        "id": "doc-int",
        "embedding": [0.1, 0.2, 0.3],
        "metadata": {"tenant": tenant_id},
    }
    await store.upsert_embeddings(tenant_id, [payload])
    results = await store.search(tenant_id, [0.1, 0.2, 0.3], limit=1)
    assert results and results[0].id == "doc-int"

    await store._client.delete_collection(store._collection_name(tenant_id))
    await store._client.close()
