"""Chat endpoints exposing the RAG pipeline over HTTP."""
from __future__ import annotations

from time import perf_counter
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from backend.app.config import Settings, settings_dependency
from backend.app.logging import get_logger
from backend.app.schemas.chat import (
    ChatMetadataFilters,
    ChatQueryRequest,
    ChatQueryResponse,
    CitationSchema,
    TokenUsageSchema,
)
from backend.rag import get_rag_pipeline
from backend.rag.llm_client import LLMClientError, LLMTimeoutError
from backend.rag.pipeline import RAGPipeline
from backend.retrieval.models import RetrievalFilters

_logger = get_logger(__name__)
_AUTH_HEADER = {"WWW-Authenticate": "API-Key"}


async def require_chat_api_key(
    x_chat_api_key: Optional[str] = Header(default=None, alias="X-Chat-API-Key"),
    settings: Settings = Depends(settings_dependency),
) -> None:
    """Ensure chat requests present the configured API key."""

    expected = settings.chat_api_key
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat API is not enabled",
        )
    if not x_chat_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Chat-API-Key header",
            headers=_AUTH_HEADER,
        )
    if x_chat_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid chat API key",
            headers=_AUTH_HEADER,
        )


router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_chat_api_key)])


def _convert_filters(filters: ChatMetadataFilters | None) -> RetrievalFilters | None:
    if filters is None:
        return None
    return RetrievalFilters(
        source_type=filters.source_type,
        tags=filters.tags,
        visibility_scope=filters.visibility_scope,
    )


@router.post("/query", response_model=ChatQueryResponse, status_code=status.HTTP_200_OK)
async def chat_query(
    request: ChatQueryRequest,
    pipeline: RAGPipeline = Depends(get_rag_pipeline),
    settings: Settings = Depends(settings_dependency),
) -> ChatQueryResponse:
    tenant_id = request.tenant_id or settings.ingest_default_tenant
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id is required")

    filters = _convert_filters(request.filters)

    start = perf_counter()
    try:
        result = await pipeline.generate_answer(
            query=request.query,
            tenant_id=tenant_id,
            filters=filters,
        )
    except LLMTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc) or "Chat completion timed out",
        ) from exc
    except LLMClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc) or "Chat completion failed",
        ) from exc

    api_latency_ms = (perf_counter() - start) * 1000
    citations = [CitationSchema.model_validate(citation) for citation in result.citations]
    token_usage = TokenUsageSchema.model_validate(result.token_usage)

    response = ChatQueryResponse(
        answer=result.answer,
        citations=citations,
        token_usage=token_usage,
        model=result.model,
        prompt_id=result.prompt_id,
        latency_ms=result.latency_ms,
    )

    _logger.info(
        "chat.query.completed",
        tenant_id=tenant_id,
        prompt_id=result.prompt_id,
        latency_ms=result.latency_ms,
        api_latency_ms=api_latency_ms,
        chunk_count=len(result.citations),
        citation_count=len(result.citations),
    )
    # TODO: add request rate limiting and abuse protections.

    return response


__all__ = ["router", "require_chat_api_key"]
