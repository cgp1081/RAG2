"""Debug CLI commands for retrieval."""
from __future__ import annotations

import asyncio
from typing import Optional

import httpx
import typer

from backend.app.config import get_settings
from backend.retrieval.models import RetrievalFilters
from backend.retrieval.service import RetrievalService
from backend.services import build_embedding_service, build_vector_store


async def _execute_debug_retrieve(
    *,
    query: str,
    tenant: str,
    limit: Optional[int],
    source_types: list[str],
    tags: list[str],
    visibility_scope: Optional[str],
) -> None:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.vector_timeout_seconds) as http_client:
        embedding_service = build_embedding_service(settings, http_client)
        vector_store = build_vector_store(settings)
        try:
            filters = RetrievalFilters(
                source_type=source_types or None,
                tags=tags or None,
                visibility_scope=visibility_scope,
            )
            service = RetrievalService(
                embedding_service=embedding_service,
                vector_store=vector_store,
                settings=settings,
            )
            response = await service.retrieve(
                query=query,
                tenant_id=tenant,
                filters=None if filters.is_empty() else filters,
                top_k=limit,
            )
        finally:
            await vector_store.close()

    if not response.chunks:
        typer.echo("No chunks matched the current query/filters.")
        return

    typer.echo(f"Retrieved {len(response.chunks)} chunk(s):")
    for index, chunk in enumerate(response.chunks, start=1):
        snippet = chunk.content.strip().replace("\n", " ")
        if len(snippet) > 160:
            snippet = f"{snippet[:157]}..."
        typer.echo(
            f"{index:02d}. doc={chunk.document_id} chunk={chunk.chunk_id} "
            f"score={chunk.normalized_score:.3f} raw={chunk.score:.3f} "
            f"scope={chunk.metadata.get('visibility_scope', 'n/a')}\n    {snippet or '(no content)'}"
        )

    if response.diagnostics:
        typer.echo("\nDiagnostics:")
        for key, value in response.diagnostics.items():
            typer.echo(f"  - {key}: {value}")


def debug_retrieve(  # pragma: no cover - thin Typer wrapper
    query: str = typer.Option(..., "--query", help="Natural language query to embed and search."),
    tenant: str = typer.Option(..., "--tenant", help="Tenant identifier to query."),
    limit: Optional[int] = typer.Option(None, "--limit", min=1, help="Override the number of chunks to request."),
    source_type: list[str] = typer.Option(
        [],
        "--source-type",
        help="Restrict results to the given source types (repeatable).",
    ),
    tag: list[str] = typer.Option(
        [],
        "--tag",
        help="Require chunks to include one of the provided tags (repeatable).",
    ),
    visibility_scope: Optional[str] = typer.Option(
        None,
        "--visibility-scope",
        help="Filter by visibility scope (e.g. employee, public).",
    ),
) -> None:
    """Run a retrieval query against the vector store for diagnostics."""

    asyncio.run(
        _execute_debug_retrieve(
            query=query,
            tenant=tenant,
            limit=limit,
            source_types=source_type,
            tags=tag,
            visibility_scope=visibility_scope,
        )
    )
