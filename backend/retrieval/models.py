"""Data models supporting retrieval workflows."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RetrievalFilters:
    """Optional metadata constraints for retrieval requests."""

    source_type: list[str] | None = None
    tags: list[str] | None = None
    visibility_scope: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a serialisable dictionary without empty entries."""

        payload: dict[str, Any] = {}
        if self.source_type:
            payload["source_type"] = list(self.source_type)
        if self.tags:
            payload["tags"] = list(self.tags)
        if self.visibility_scope:
            payload["visibility_scope"] = self.visibility_scope
        return payload

    def is_empty(self) -> bool:
        """Return True when no filters are set."""

        return not any([self.source_type, self.tags, self.visibility_scope])


@dataclass(slots=True)
class RetrievedChunk:
    """Represents a chunk returned from retrieval."""

    chunk_id: str
    document_id: str
    tenant_id: str
    score: float
    normalized_score: float
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalRequest:
    """Internal representation of a retrieval invocation."""

    query: str
    tenant_id: str
    filters: RetrievalFilters | None
    top_k: int
    score_floor: float


@dataclass(slots=True)
class RetrievalResponse:
    """Structured response returned by the retrieval service."""

    chunks: list[RetrievedChunk]
    applied_filters: RetrievalFilters | None
    diagnostics: dict[str, Any] = field(default_factory=dict)
