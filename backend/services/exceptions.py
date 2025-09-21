"""Custom exception types for backend service abstractions."""


class VectorStoreError(Exception):
    """Base error for vector store operations."""


class VectorCollectionError(VectorStoreError):
    """Raised when collection creation or validation fails."""


class VectorUpsertError(VectorStoreError):
    """Raised when embedding upsert requests fail."""


class VectorSearchError(VectorStoreError):
    """Raised when vector search operations fail."""


class EmbeddingServiceError(Exception):
    """Base error for embedding service operations."""


class EmbeddingTimeoutError(EmbeddingServiceError):
    """Raised when embedding requests exceed the configured timeout."""


class EmbeddingRetryableError(EmbeddingServiceError):
    """Raised for transient embedding failures that may succeed on retry."""
