"""Pydantic schemas for retrieval API endpoints."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RetrievalFilterSchema(BaseModel):
    source_type: list[str] | None = Field(default=None, description="Allowed source types")
    tags: list[str] | None = Field(default=None, description="Required tags")
    visibility_scope: str | None = Field(default=None, description="Visibility scope to enforce")


class RetrievalQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query to retrieve chunks for")
    tenant_id: str | None = Field(default=None, description="Tenant identifier; defaults to settings")
    top_k: int | None = Field(default=None, ge=1, description="Override number of chunks to request")
    filters: RetrievalFilterSchema | None = Field(default=None, description="Optional metadata filters")


class RetrievalChunkResponse(BaseModel):
    chunk_id: str
    document_id: str
    tenant_id: str
    score: float
    normalized_score: float
    content: str
    metadata: dict[str, Any]


class RetrievalQueryResponse(BaseModel):
    chunks: list[RetrievalChunkResponse]
    applied_filters: dict[str, Any] | None
    diagnostics: dict[str, Any]
