"""FastAPI dependencies for RAG pipeline wiring."""
from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from fastapi import Depends

from backend.app.config import Settings, settings_dependency
from backend.app.logging import get_logger
from backend.rag.llm_client import build_llm_client
from backend.rag.pipeline import RAGPipeline
from backend.rag.prompts import PromptBuilder
from backend.retrieval.dependencies import get_retrieval_service
from backend.retrieval.service import RetrievalService

_logger = get_logger(__name__)


async def get_rag_pipeline(
    settings: Settings = Depends(settings_dependency),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> AsyncIterator[RAGPipeline]:
    """Yield a configured RAG pipeline for the request scope."""

    timeout = settings.llm_timeout_seconds
    async with httpx.AsyncClient(timeout=timeout) as http_client:
        llm_client = build_llm_client(settings, http_client)
        pipeline = RAGPipeline(
            retrieval_service=retrieval_service,
            llm_client=llm_client,
            prompt_builder=PromptBuilder(),
            settings=settings,
            logger=_logger,
        )
        yield pipeline


__all__ = ["get_rag_pipeline"]
