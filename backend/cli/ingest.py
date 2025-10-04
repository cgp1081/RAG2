"""CLI commands for document ingestion workflows."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer

from backend.app.config import get_settings
from backend.cli.run_ingest import run_ingest
from backend.db import SessionLocal
from backend.db.models import Tenant
from backend.structured.ingest import StructuredTableIngestion


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


def ingest_table(
    csv: Path = typer.Option(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the CSV file to ingest",
    ),
    table_name: str = typer.Option(..., help="Structured table name (slug)"),
    tenant: Optional[str] = typer.Option(
        None, help="Tenant slug (defaults to settings.ingest_default_tenant)"
    ),
    max_rows: Optional[int] = typer.Option(None, min=1, help="Override maximum allowed rows"),
    sample_size: Optional[int] = typer.Option(
        None,
        min=1,
        help="Override sample size for column stats",
    ),
) -> None:
    """Ingest a CSV into structured storage for table question answering."""

    settings = get_settings()
    resolved_tenant = tenant or settings.ingest_default_tenant

    session = SessionLocal()
    try:
        tenant_row = (
            session.query(Tenant)
            .filter(Tenant.slug == resolved_tenant)
            .one_or_none()
        )
        if tenant_row is None:
            typer.secho(f"Tenant '{resolved_tenant}' not found", fg=typer.colors.RED)
            raise typer.Exit(code=1)

        pipeline = StructuredTableIngestion()

        async def _runner() -> None:
            table = await pipeline.ingest_csv(
                path=csv,
                table_name=table_name,
                tenant_id=tenant_row.id,
                settings=settings,
                session=session,
                max_rows=max_rows,
                sample_size=sample_size,
            )
            typer.secho(
                f"Structured table '{table_name}' ready (version {table.version}, rows {table.row_count}).",
                fg=typer.colors.GREEN,
            )

        try:
            asyncio.run(_runner())
        except Exception as exc:  # pragma: no cover - CLI surface
            typer.secho(f"Structured ingestion failed: {exc}", fg=typer.colors.RED)
            raise typer.Exit(code=1) from exc
    finally:
        session.close()
