"""Pydantic schemas for structured query endpoints."""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class StructuredQueryRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant slug or identifier")
    table_name: str = Field(..., description="Structured table name")
    sql: str = Field(..., description="Validated SQL query")


class StructuredColumnSchema(BaseModel):
    name: str
    data_type: str | None = None

    model_config = ConfigDict(from_attributes=True)


class StructuredQueryResponse(BaseModel):
    columns: List[StructuredColumnSchema]
    rows: List[Dict[str, Any]]
    row_count: int
    execution_ms: float
    log_id: str

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "StructuredQueryRequest",
    "StructuredQueryResponse",
    "StructuredColumnSchema",
]
