"""Command-line interface entry point for the RAG platform."""
from __future__ import annotations

import typer

from .debug import debug_retrieve
from .dry_run import dry_run
from .dry_run_sql import dry_run_sql
from .eval import eval_command
from .ingest import ingest_files, ingest_table
from .voice import voice_simulate

app = typer.Typer(help="RAG platform management commands")
app.command("ingest-files")(ingest_files)
app.command("debug-retrieve")(debug_retrieve)
app.command("dry-run")(dry_run)
app.command("ingest-table")(ingest_table)
app.command("dry-run-sql")(dry_run_sql)
app.command("eval")(eval_command)
app.command("voice-simulate")(voice_simulate)

__all__ = ["app"]
