"""Developer dry-run command for RAG answer generation."""
from __future__ import annotations

import asyncio
from typing import Optional

import httpx
import typer

from backend.app.config import get_settings
from backend.rag.llm_client import build_llm_client
from backend.rag.pipeline import RAGPipeline
from backend.rag.prompts import PromptBuilder
from backend.retrieval.models import RetrievalFilters
from backend.retrieval.service import RetrievalService
from backend.services import build_embedding_service, build_vector_store


async def _execute_dry_run(
    *,
    query: str,
    tenant: str,
    source_types: list[str],
    tags: list[str],
    visibility_scope: Optional[str],
) -> None:
    settings = get_settings()
    prompt_builder = PromptBuilder()
    vector_store = build_vector_store(settings)

    try:
        async with httpx.AsyncClient(timeout=settings.vector_timeout_seconds) as embedding_client:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as llm_client_http:
                embedding_service = build_embedding_service(settings, embedding_client)
                llm_client = build_llm_client(settings, llm_client_http)
                retrieval_service = RetrievalService(
                    embedding_service=embedding_service,
                    vector_store=vector_store,
                    settings=settings,
                )
                pipeline = RAGPipeline(
                    retrieval_service=retrieval_service,
                    llm_client=llm_client,
                    prompt_builder=prompt_builder,
                    settings=settings,
                )

                filters = RetrievalFilters(
                    source_type=source_types or None,
                    tags=tags or None,
                    visibility_scope=visibility_scope,
                )
                result = await pipeline.generate_answer(
                    query=query,
                    tenant_id=tenant,
                    filters=None if filters.is_empty() else filters,
                )
    finally:
        await vector_store.close()

    typer.echo("=== Rendered Prompt ===")
    typer.echo(result.prompt)
    typer.echo("")

    typer.echo("=== Answer ===")
    typer.echo(result.answer)
    typer.echo("")

    typer.echo("=== Token Usage ===")
    typer.echo(
        f"prompt={result.token_usage.prompt_tokens} "
        f"completion={result.token_usage.completion_tokens} "
        f"total={result.token_usage.total_tokens}"
    )
    typer.echo("")

    if result.citations:
        typer.echo("=== Citations ===")
        for idx, citation in enumerate(result.citations, start=1):
            snippet = citation.snippet.replace("\n", "\n    ")
            typer.echo(
                f"[{idx}] document_id={citation.document_id} "
                f"score={citation.score:.3f} normalized={citation.normalized_score:.3f}"
            )
            typer.echo(f"    {snippet if snippet else '(no snippet)'}")
    else:
        typer.echo("=== Citations ===")
        typer.echo("(none)")


def dry_run(  # pragma: no cover - Typer entry point
    query: str = typer.Option(..., "--query", help="User question to dry-run through the pipeline."),
    tenant: Optional[str] = typer.Option(
        None,
        "--tenant",
        help="Tenant identifier (defaults to settings.ingest_default_tenant).",
    ),
    source_type: list[str] = typer.Option(
        [],
        "--source-type",
        help="Restrict context to the given source_type values (repeatable).",
    ),
    tag: list[str] = typer.Option(
        [],
        "--tag",
        help="Restrict context to chunks carrying one of these tags (repeatable).",
    ),
    visibility_scope: Optional[str] = typer.Option(
        None,
        "--visibility-scope",
        help="Filter context to a specific visibility scope.",
    ),
) -> None:
    """Run the full RAG pipeline locally and print the prompt, answer, and citations."""

    settings = get_settings()
    resolved_tenant = tenant or settings.ingest_default_tenant
    asyncio.run(
        _execute_dry_run(
            query=query,
            tenant=resolved_tenant,
            source_types=source_type,
            tags=tag,
            visibility_scope=visibility_scope,
        )
    )


__all__ = ["dry_run"]
