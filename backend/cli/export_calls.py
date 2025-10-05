"""CLI command for exporting call summaries to CSV."""
from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import typer
from sqlalchemy import func

from backend.db.models import CallSession
from backend.db.session import SessionLocal


def _parse_date(value: str | None) -> Optional[date]:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def export_calls(  # pragma: no cover - Typer entry point
    date_from: Optional[str] = typer.Option(None, "--from", help="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = typer.Option(None, "--to", help="End date (YYYY-MM-DD)"),
    tenant: Optional[str] = typer.Option(None, "--tenant", help="Tenant UUID"),
    output: Path = typer.Option(Path("reports/calls.csv"), "--output", path_type=Path),
) -> None:
    start = _parse_date(date_from)
    end = _parse_date(date_to)

    output.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as session:
        query = session.query(CallSession)
        if tenant:
            query = query.filter(CallSession.tenant_id == tenant)
        if start:
            query = query.filter(func.date(CallSession.created_at) >= start)  # type: ignore[name-defined]
        if end:
            query = query.filter(func.date(CallSession.created_at) <= end)  # type: ignore[name-defined]
        query = query.order_by(CallSession.created_at.asc())

        rows = query.all()

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "call_id",
                "tenant_id",
                "status",
                "confidence",
                "escalated",
                "started_at",
                "ended_at",
                "transcript",
            ]
        )
        for call in rows:
            writer.writerow(
                [
                    call.id,
                    call.tenant_id,
                    call.status,
                    call.confidence,
                    call.escalated,
                    call.created_at,
                    call.ended_at,
                    (call.transcript or "").replace("\n", " "),
                ]
            )

    typer.echo(f"Exported {len(rows)} calls to {output}")


__all__ = ["export_calls"]
