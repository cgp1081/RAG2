"""Command-line interface entry point for the RAG platform."""
from __future__ import annotations

import typer

from .debug import debug_retrieve
from .ingest import ingest_files

app = typer.Typer(help="RAG platform management commands")
app.command("ingest-files")(ingest_files)
app.command("debug-retrieve")(debug_retrieve)

__all__ = ["app"]
