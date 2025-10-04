"""CLI helper for running structured SQL queries locally."""
from __future__ import annotations

import typer
from sqlalchemy import select

from backend.app.config import get_settings
from backend.db import SessionLocal
from backend.db.models import StructuredTable, Tenant
from backend.structured.query_service import GuardViolation, build_query_service


def dry_run_sql(
    query: str = typer.Option(..., "--query", help="SQL SELECT query to execute"),
    tenant: str = typer.Option(..., "--tenant", help="Tenant slug"),
    table: str = typer.Option(..., "--table", help="Structured table name"),
) -> None:
    """Execute a structured SQL query and print the results."""

    settings = get_settings()
    session = SessionLocal()
    try:
        tenant_row = session.execute(select(Tenant).where(Tenant.slug == tenant)).scalar_one_or_none()
        if tenant_row is None:
            typer.secho(f"Tenant '{tenant}' not found", fg=typer.colors.RED)
            raise typer.Exit(code=1)

        table_row = (
            session.execute(
                select(StructuredTable)
                .where(StructuredTable.tenant_id == tenant_row.id)
                .where(StructuredTable.table_name == table)
                .order_by(StructuredTable.version.desc())
                .limit(1)
            ).scalar_one_or_none()
        )
        if table_row is None:
            typer.secho(f"Structured table '{table}' not found", fg=typer.colors.RED)
            raise typer.Exit(code=1)

        service = build_query_service(settings, session)
        try:
            result = service.execute(query=query, tenant_id=tenant_row.id, table_name=table)
        except GuardViolation as exc:
            typer.secho(f"Query blocked: {exc}", fg=typer.colors.YELLOW)
            raise typer.Exit(code=1)

        typer.echo(f"Query succeeded (rows: {result.row_count}, duration: {result.execution_ms:.2f} ms)")
        if result.rows:
            columns = [col.name for col in result.columns]
            header = " | ".join(columns)
            typer.echo(header)
            typer.echo("-" * len(header))
            for row in result.rows[: min(10, len(result.rows))]:
                typer.echo(" | ".join(str(row.values.get(col, "")) for col in columns))
        else:
            typer.echo("(no rows returned)")
    finally:
        session.close()


__all__ = ["dry_run_sql"]
