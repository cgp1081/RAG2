"""CLI wrapper for computing daily call metrics."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import typer

from backend.voice.summary import compute_daily_metrics


def _parse_date(value: Optional[str]) -> Optional[datetime.date]:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def voice_call_summary(  # pragma: no cover - Typer entry point
    date_from: Optional[str] = typer.Option(None, "--from", help="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = typer.Option(None, "--to", help="End date (YYYY-MM-DD)"),
) -> None:
    start = _parse_date(date_from)
    end = _parse_date(date_to)

    rows = asyncio.run(compute_daily_metrics(start=start, end=end))
    typer.echo(f"Computed {rows} daily metric rows")


__all__ = ["voice_call_summary"]
