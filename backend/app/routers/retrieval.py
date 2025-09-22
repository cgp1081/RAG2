"""Retrieval endpoints for querying indexed content."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, settings_dependency
from backend.app.schemas.retrieval import (
    RetrievalChunkResponse,
    RetrievalFilterSchema,
    RetrievalQueryRequest,
    RetrievalQueryResponse,
)
from backend.retrieval.dependencies import get_retrieval_service
from backend.retrieval.models import RetrievalFilters
from backend.retrieval.service import RetrievalService

router = APIRouter(prefix="/v1/retrieval", tags=["retrieval"])


def _convert_filters(filters: RetrievalFilterSchema | None) -> RetrievalFilters | None:
    if filters is None:
        return None
    return RetrievalFilters(
        source_type=filters.source_type,
        tags=filters.tags,
        visibility_scope=filters.visibility_scope,
    )


@router.post("/query", response_model=RetrievalQueryResponse, status_code=status.HTTP_200_OK)
async def query_retrieval(
    request: RetrievalQueryRequest,
    service: RetrievalService = Depends(get_retrieval_service),
    settings: Settings = Depends(settings_dependency),
) -> RetrievalQueryResponse:
    tenant_id = request.tenant_id or settings.ingest_default_tenant
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id is required")

    filters = _convert_filters(request.filters)
    response = await service.retrieve(
        query=request.query,
        tenant_id=tenant_id,
        filters=filters,
        top_k=request.top_k,
    )

    chunks = [
        RetrievalChunkResponse(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            tenant_id=chunk.tenant_id,
            score=chunk.score,
            normalized_score=chunk.normalized_score,
            content=chunk.content,
            metadata=chunk.metadata,
        )
        for chunk in response.chunks
    ]

    applied_filters = (
        response.applied_filters.as_dict() if response.applied_filters else None
    )

    return RetrievalQueryResponse(
        chunks=chunks,
        applied_filters=applied_filters,
        diagnostics=response.diagnostics,
    )


__all__ = ["router"]
