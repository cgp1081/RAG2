"""FastAPI dependencies for retrieval service wiring."""
from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from fastapi import Depends

from backend.app.config import Settings, settings_dependency
from backend.retrieval.service import RetrievalService
from backend.services import build_embedding_service, build_vector_store


async def get_retrieval_service(
    settings: Settings = Depends(settings_dependency),
) -> AsyncIterator[RetrievalService]:
    """Yield a retrieval service instance with request-scoped resources."""

    async with httpx.AsyncClient(timeout=settings.vector_timeout_seconds) as http_client:
        embedding_service = build_embedding_service(settings, http_client)
        vector_store = build_vector_store(settings)
        service = RetrievalService(
            embedding_service=embedding_service,
            vector_store=vector_store,
            settings=settings,
        )
        try:
            yield service
        finally:
            await vector_store.close()
