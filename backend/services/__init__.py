"""Service layer exports for the backend."""

from .embedding_service import EmbeddingService, build_embedding_service
from .exceptions import (
    EmbeddingRetryableError,
    EmbeddingServiceError,
    EmbeddingTimeoutError,
    VectorCollectionError,
    VectorSearchError,
    VectorStoreError,
    VectorUpsertError,
)
from .vector_store import (
    VectorPayload,
    VectorSearchResult,
    VectorStoreClient,
    build_vector_store,
)

__all__ = [
    "EmbeddingService",
    "EmbeddingRetryableError",
    "EmbeddingServiceError",
    "EmbeddingTimeoutError",
    "VectorCollectionError",
    "VectorSearchError",
    "VectorStoreClient",
    "VectorStoreError",
    "VectorUpsertError",
    "VectorPayload",
    "VectorSearchResult",
    "build_embedding_service",
    "build_vector_store",
]
