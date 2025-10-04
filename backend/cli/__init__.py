"""Command-line interface entry point for the RAG platform."""
from __future__ import annotations

import typer

from .debug import debug_retrieve
from .dry_run import dry_run
from .dry_run_sql import dry_run_sql
from .ingest import ingest_files, ingest_table

app = typer.Typer(help="RAG platform management commands")
app.command("ingest-files")(ingest_files)
app.command("debug-retrieve")(debug_retrieve)
app.command("dry-run")(dry_run)
app.command("ingest-table")(ingest_table)
app.command("dry-run-sql")(dry_run_sql)

__all__ = ["app"]
