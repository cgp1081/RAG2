"""Async Qdrant client wrapper for multi-tenant vector storage."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Sequence, TypedDict

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import CollectionInfo, Distance, VectorParams
from structlog.types import FilteringBoundLogger
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential_jitter

from backend.app.config import Settings
from backend.app.logging import get_logger
from backend.services.exceptions import (
    VectorCollectionError,
    VectorSearchError,
    VectorStoreError,
    VectorUpsertError,
)

RetryFactory = Callable[[], AsyncRetrying]


class VectorPayload(TypedDict):
    """Payload describing a single vector upsert."""

    id: str
    embedding: Sequence[float]
    metadata: dict[str, Any]


@dataclass(slots=True)
class VectorSearchResult:
    """Result container for vector search responses."""

    id: str
    score: float
    metadata: dict[str, Any]


class VectorStoreClient:
    """Encapsulates Qdrant operations for tenant-scoped collections."""

    def __init__(
        self,
        client: AsyncQdrantClient,
        collection_prefix: str,
        vector_dim: int,
        *,
        distance: str = "Cosine",
        timeout: float = 10.0,
        retry_factory: RetryFactory | None = None,
        logger: FilteringBoundLogger | None = None,
    ) -> None:
        self._client = client
        self._collection_prefix = collection_prefix
        self.vector_dim = vector_dim
        self.timeout = timeout
        self._distance = Distance[distance.upper()]
        self._retry_factory = retry_factory or self._default_retry_factory
        self._logger = logger or get_logger(__name__)

    @staticmethod
    def _default_retry_factory() -> AsyncRetrying:
        return AsyncRetrying(
            wait=wait_exponential_jitter(initial=0.5, max=5.0),
            stop=stop_after_attempt(3),
            reraise=True,
        )

    def _collection_name(self, tenant_id: str) -> str:
        return f"{self._collection_prefix}_{tenant_id}"

    async def ensure_collection(self, tenant_id: str) -> str:
        """Ensure a tenant-specific collection exists with the expected config."""

        name = self._collection_name(tenant_id)
        try:
            info = await self._client.get_collection(name, timeout=self.timeout)
        except UnexpectedResponse:
            await self._create_collection(name)
            return name
        except Exception as exc:  # pragma: no cover - defensive logging
            raise VectorCollectionError(f"Failed to fetch collection {name}: {exc}") from exc

        existing_dim = self._extract_vector_dim(info)
        if existing_dim != self.vector_dim:
            raise VectorCollectionError(
                f"Collection {name} has dimension {existing_dim}, expected {self.vector_dim}"
            )
        return name

    async def _create_collection(self, name: str) -> None:
        vector_params = VectorParams(size=self.vector_dim, distance=self._distance)
        try:
            async for attempt in self._retry_factory():
                with attempt:
                    await self._client.create_collection(
                        name,
                        vectors_config=vector_params,
                        timeout=self.timeout,
                    )
        except Exception as exc:  # pragma: no cover - retry exhaustion
            self._logger.error("collection.create.failed", collection=name, error=str(exc))
            raise VectorCollectionError(f"Unable to create collection {name}: {exc}") from exc
        else:
            self._logger.info("collection.created", collection=name, vector_dim=self.vector_dim)

    async def upsert_embeddings(self, tenant_id: str, vectors: Iterable[VectorPayload]) -> None:
        """Upsert embeddings into the tenant collection."""

        points = [
            {
                "id": payload["id"],
                "vector": list(payload["embedding"]),
                "payload": payload["metadata"],
            }
            for payload in vectors
        ]
        if not points:
            return

        collection = self._collection_name(tenant_id)
        try:
            async for attempt in self._retry_factory():
                with attempt:
                    await self._client.upsert(
                        collection_name=collection,
                        points=points,
                        wait=True,
                        timeout=self.timeout,
                    )
        except Exception as exc:  # pragma: no cover - retry exhaustion
            self._logger.error("vector.upsert.failed", collection=collection, error=str(exc))
            raise VectorUpsertError(f"Failed to upsert embeddings for {collection}: {exc}") from exc
        else:
            self._logger.info(
                "vector.upsert", collection=collection, count=len(points)
            )

    async def search(
        self,
        tenant_id: str,
        embedding: Sequence[float],
        *,
        limit: int = 10,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[VectorSearchResult]:
        """Search for nearest vectors within a tenant collection."""

        collection = self._collection_name(tenant_id)
        try:
            async for attempt in self._retry_factory():
                with attempt:
                    scored = await self._client.search(
                        collection_name=collection,
                        query_vector=list(embedding),
                        limit=limit,
                        filter=filters,
                        timeout=self.timeout,
                    )
        except Exception as exc:  # pragma: no cover - retry exhaustion
            self._logger.error("vector.search.failed", collection=collection, error=str(exc))
            raise VectorSearchError(f"Search failed for {collection}: {exc}") from exc

        results: list[VectorSearchResult] = []
        for point in scored:
            payload = getattr(point, "payload", {}) or {}
            results.append(
                VectorSearchResult(
                    id=str(getattr(point, "id", "")),
                    score=float(getattr(point, "score", 0.0)),
                    metadata=dict(payload),
                )
            )
        return results

    async def healthcheck(self) -> None:
        """Verify vector store availability."""

        try:
            async for attempt in self._retry_factory():
                with attempt:
                    await self._client.get_collections(timeout=self.timeout)
        except Exception as exc:  # pragma: no cover - retry exhaustion
            self._logger.error("vector.healthcheck.failed", error=str(exc))
            raise VectorStoreError(f"Vector store unavailable: {exc}") from exc

    def _extract_vector_dim(self, info: CollectionInfo) -> int:
        vectors = info.config.params.vectors
        if isinstance(vectors, dict):
            first_config = next(iter(vectors.values()))
            return first_config.size
        return vectors.size


def build_vector_store(settings: Settings) -> VectorStoreClient:
    """Factory for a configured VectorStoreClient instance."""

    client = AsyncQdrantClient(
        url=str(settings.qdrant_url),
        api_key=settings.qdrant_api_key,
        timeout=settings.vector_timeout_seconds,
    )
    return VectorStoreClient(
        client,
        collection_prefix="tenant",
        vector_dim=settings.vector_dim,
        timeout=settings.vector_timeout_seconds,
    )
