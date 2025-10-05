"""Pydantic schemas for call analytics APIs."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CallTurnSchema(BaseModel):
    sequence: int
    speaker: str
    text: str
    confidence: Optional[float]
    started_at: Optional[datetime]
    ended_at: Optional[datetime]


class CallSummarySchema(BaseModel):
    id: str
    tenant_id: str
    caller_number: Optional[str]
    status: str
    confidence: Optional[float]
    escalated: bool
    started_at: datetime
    ended_at: Optional[datetime]
    handle_seconds: Optional[float]
    recording_url: Optional[str]
    transcript_preview: Optional[str]


class CallDetailSchema(CallSummarySchema):
    transcript: Optional[str]
    turns: List[CallTurnSchema] = Field(default_factory=list)
    caller_metadata: dict | None = None
    storage_object_key: Optional[str]


class PaginatedCallsSchema(BaseModel):
    items: List[CallSummarySchema]
    total: int
    page: int
    page_size: int


class DailyMetricSchema(BaseModel):
    tenant_id: str
    date: date
    total_calls: int
    escalations: int
    avg_confidence: Optional[float]
    avg_handle_seconds: Optional[float]


__all__ = [
    "CallSummarySchema",
    "CallDetailSchema",
    "CallTurnSchema",
    "PaginatedCallsSchema",
    "DailyMetricSchema",
]
