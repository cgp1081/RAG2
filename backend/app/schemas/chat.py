"""Pydantic schemas for chat endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, constr

from backend.app.schemas.structured import StructuredColumnSchema


class ChatMetadataFilters(BaseModel):
    """Metadata filters for chat queries."""

    source_type: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    visibility_scope: Optional[str] = None


class ChatQueryRequest(BaseModel):
    """Incoming chat query payload."""

    query: constr(min_length=1)
    tenant_id: Optional[str] = None
    filters: Optional[ChatMetadataFilters] = None
    structured_query: Optional[str] = None
    structured_table: Optional[str] = None
    allow_structured: bool = False


class CitationSchema(BaseModel):
    """LLM citation metadata returned to clients."""

    document_id: str
    chunk_id: str
    score: float
    normalized_score: float
    source_type: Optional[str] = None
    title: Optional[str] = None
    snippet: str

    model_config = ConfigDict(from_attributes=True)


class TokenUsageSchema(BaseModel):
    """Token accounting for chat responses."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    model_config = ConfigDict(from_attributes=True)


class ChatTableResult(BaseModel):
    table_name: str
    columns: List[StructuredColumnSchema]
    rows: List[Dict[str, Any]]
    row_count: int
    execution_ms: float

    model_config = ConfigDict(from_attributes=True)


class ChatQueryResponse(BaseModel):
    """Payload returned from the chat query endpoint."""

    answer: str
    citations: List[CitationSchema]
    token_usage: TokenUsageSchema
    model: str
    prompt_id: str
    latency_ms: float
    table: Optional[ChatTableResult] = None

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "ChatMetadataFilters",
    "ChatQueryRequest",
    "CitationSchema",
    "TokenUsageSchema",
    "ChatQueryResponse",
]
