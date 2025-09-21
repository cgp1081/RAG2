"""CLI commands for document ingestion workflows."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer

from backend.app.config import get_settings
from backend.cli.run_ingest import run_ingest


def ingest_files(
    path: Path = typer.Option(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Directory containing documents to ingest",
    ),
    tenant: Optional[str] = typer.Option(
        None, help="Tenant identifier (defaults to settings.ingest_default_tenant)"
    ),
    infer_metadata: bool = typer.Option(
        False, help="Attempt to infer metadata such as title/author"
    ),
    batch_size: int = typer.Option(50, min=1, help="Batch size for embedding upserts"),
) -> None:
    """Ingest local files into the RAG knowledge base."""

    settings = get_settings()
    resolved_tenant = tenant or settings.ingest_default_tenant

    asyncio.run(
        run_ingest(
            path=path,
            tenant_id=resolved_tenant,
            infer_metadata=infer_metadata,
            batch_size=batch_size,
        )
    )
