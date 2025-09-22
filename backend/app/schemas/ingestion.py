"""Pydantic schemas for admin ingestion status endpoints."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class IngestionRunSummary(BaseModel):
    id: UUID
    tenant_id: UUID
    status: str
    source_id: UUID | None
    source_name: str | None
    source_type: str | None
    path: str | None
    total_documents: int
    processed_documents: int
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: float | None
    error: str | None

    class Config:
        orm_mode = True


class PaginatedIngestionRuns(BaseModel):
    items: list[IngestionRunSummary]
    total: int
    page: int
    page_size: int


class DocumentStatus(BaseModel):
    id: UUID
    tenant_id: UUID
    source_id: UUID | None
    source_name: str | None
    source_type: str | None
    title: str | None
    status: str
    chunk_count: int
    last_ingested_at: datetime | None
    sha256: str
    mime_type: str | None

    class Config:
        orm_mode = True


class PaginatedDocuments(BaseModel):
    items: list[DocumentStatus]
    total: int
    page: int
    page_size: int
