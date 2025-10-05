"""Guarded structured SQL execution over ingested tables."""
from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

import pandas as pd
import sqlglot
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlglot import exp
from sqlglot.errors import ParseError

from backend.app.config import Settings
from backend.app.logging import get_logger
from backend.db.models import StructuredColumn, StructuredQueryLog, StructuredRow, StructuredTable

_LOGGER = get_logger(__name__)
_MAX_LIMIT = 50


class GuardViolation(Exception):
    """Raised when a SQL query fails guard validation."""


@dataclass(slots=True)
class ColumnMeta:
    name: str
    data_type: str | None = None


@dataclass(slots=True)
class TableRow:
    values: dict[str, Any]


@dataclass(slots=True)
class QueryResult:
    table_id: uuid.UUID
    table_name: str
    columns: list[ColumnMeta]
    rows: list[TableRow]
    row_count: int
    execution_ms: float
    log_id: uuid.UUID


@dataclass(slots=True)
class QueryRequest:
    tenant_id: uuid.UUID
    table_name: str
    sql: str


class SQLGuard:
    """Static SQL validation enforcing query safety limits."""

    def __init__(self, *, allowed_functions: Sequence[str], max_limit: int = _MAX_LIMIT) -> None:
        self.allowed_functions = {func.lower() for func in allowed_functions}
        self.max_limit = max_limit

    def validate(self, sql: str, *, table_name: str, column_count: int) -> str:
        try:
            expression = sqlglot.parse_one(sql)
        except ParseError as exc:  # pragma: no cover - exercised via tests
            raise GuardViolation(f"Invalid SQL syntax: {exc}") from exc

        if not isinstance(expression, exp.Select):
            raise GuardViolation("Only SELECT statements are allowed")

        # Ensure the query only references the permitted table.
        table_refs = {table.name for table in expression.find_all(exp.Table) if table.name}
        if not table_refs:
            raise GuardViolation("Query must reference a table")
        normalised_table = table_name.lower()
        if any(ref.lower() != normalised_table for ref in table_refs):
            raise GuardViolation("Query references invalid tables")

        # Reject subqueries to keep evaluation predictable.
        if any(True for _ in expression.find_all(exp.Subquery)):
            raise GuardViolation("Subqueries are not permitted")

        limit_expr = expression.args.get("limit")
        if limit_expr is None or not getattr(limit_expr, "expression", None):
            raise GuardViolation("Query must include a LIMIT clause")
        limit_value = limit_expr.expression.try_cast(int)
        if limit_value is None:
            raise GuardViolation("LIMIT must be a literal integer")
        if limit_value > self.max_limit:
            raise GuardViolation(f"LIMIT {limit_value} exceeds maximum of {self.max_limit}")

        # Disallow SELECT * for wide tables.
        if column_count > 20:
            for projection in expression.expressions:
                if isinstance(projection, exp.Star):
                    raise GuardViolation("Wildcard SELECT is not allowed for wide tables")

        # Restrict aggregate functions to allowed list.
        for func in expression.find_all(exp.Func):
            func_name = func.name.lower() if func.name else ""
            if func_name and func_name not in self.allowed_functions:
                raise GuardViolation(f"Function '{func_name}' is not permitted")

        return expression.sql()


class StructuredQueryService:
    """Executes guarded SQL queries against structured table snapshots."""

    def __init__(self, *, session: Session, settings: Settings, guard: SQLGuard) -> None:
        self._session = session
        self._settings = settings
        self._guard = guard
        self._logger = get_logger(__name__)
        self._sql_timeout = settings.sql_guard_config().timeout_seconds

    def execute(self, query: str, tenant_id: uuid.UUID, table_name: str) -> QueryResult:
        try:
            structured_table = self._resolve_table(tenant_id, table_name)
        except GuardViolation as exc:
            self._persist_log(
                tenant_id=tenant_id,
                table_id=None,
                executed_sql=query,
                status="blocked",
                reason=str(exc),
            )
            raise
        columns = self._load_columns(structured_table.id)
        column_count = len(columns)

        try:
            sanitized_sql = self._guard.validate(
                query,
                table_name=structured_table.table_name,
                column_count=column_count,
            )
        except GuardViolation as exc:
            self._persist_log(
                tenant_id=tenant_id,
                table_id=structured_table.id,
                executed_sql=query,
                status="blocked",
                reason=str(exc),
            )
            raise

        start = time.perf_counter()
        try:
            rows = self._execute_sqlite(
                structured_table.id,
                structured_table.table_name,
                sanitized_sql,
                [column.name for column in columns],
            )
        except Exception as exc:  # pragma: no cover - error path
            duration_ms = (time.perf_counter() - start) * 1000
            self._persist_log(
                tenant_id=tenant_id,
                table_id=structured_table.id,
                executed_sql=sanitized_sql,
                status="error",
                reason=str(exc),
                duration_ms=duration_ms,
            )
            self._logger.error(
                "structured.query.failed",
                tenant_id=str(tenant_id),
                table_name=table_name,
                error=str(exc),
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        row_count = len(rows)

        log = self._persist_log(
            tenant_id=tenant_id,
            table_id=structured_table.id,
            executed_sql=sanitized_sql,
            status="allowed",
            row_count=row_count,
            duration_ms=duration_ms,
        )

        column_meta = [ColumnMeta(name=col.name, data_type=col.data_type) for col in columns]
        result_rows = [TableRow(values=row) for row in rows]

        self._logger.info(
            "structured.query.executed",
            tenant_id=str(tenant_id),
            table_name=table_name,
            row_count=row_count,
            duration_ms=duration_ms,
            log_id=str(log.id),
        )

        return QueryResult(
            table_id=structured_table.id,
            table_name=structured_table.table_name,
            columns=column_meta,
            rows=result_rows,
            row_count=row_count,
            execution_ms=duration_ms,
            log_id=log.id,
        )

    # ------------------------------------------------------------------
    # Helpers

    def _resolve_table(self, tenant_id: uuid.UUID, table_name: str) -> StructuredTable:
        stmt = (
            select(StructuredTable)
            .where(StructuredTable.tenant_id == tenant_id)
            .where(StructuredTable.table_name == table_name)
            .order_by(StructuredTable.version.desc())
            .limit(1)
        )
        table = self._session.execute(stmt).scalar_one_or_none()
        if table is None:
            raise GuardViolation("Structured table not found")
        if table.status != "ready":
            raise GuardViolation("Structured table is not ready for querying")
        return table

    def _load_columns(self, table_id: uuid.UUID) -> list[StructuredColumn]:
        stmt = (
            select(StructuredColumn)
            .where(StructuredColumn.table_id == table_id)
            .order_by(StructuredColumn.column_order)
        )
        return self._session.execute(stmt).scalars().all()

    def _load_rows(self, table_id: uuid.UUID) -> pd.DataFrame:
        stmt = select(StructuredRow.payload).where(StructuredRow.table_id == table_id)
        payloads = [row.payload for row in self._session.execute(stmt).all()]
        if not payloads:
            return pd.DataFrame()
        return pd.DataFrame(payloads)

    def _execute_sqlite(
        self,
        table_id: uuid.UUID,
        table_name: str,
        sql: str,
        column_names: list[str],
    ) -> list[dict[str, Any]]:
        df = self._load_rows(table_id)
        if df.empty and column_names:
            df = pd.DataFrame(columns=column_names)
        engine = sqlite3.connect(":memory:", timeout=self._sql_timeout)
        try:
            df.to_sql(table_name, engine, index=False, if_exists="replace")
            cursor = engine.cursor()
            cursor.execute(sql)
            fetched = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            return [dict(zip(columns, row)) for row in fetched]
        finally:
            engine.close()

    def _persist_log(
        self,
        *,
        tenant_id: uuid.UUID,
        table_id: uuid.UUID | None,
        executed_sql: str,
        status: str,
        reason: str | None = None,
        row_count: int | None = None,
        duration_ms: float | None = None,
    ) -> StructuredQueryLog:
        log = StructuredQueryLog(
            tenant_id=tenant_id,
            table_id=table_id,
            executed_sql=executed_sql,
            status=status,
            reason=reason,
            row_count=row_count,
            duration_ms=duration_ms,
        )
        self._session.add(log)
        self._session.commit()
        return log


def build_query_service(settings: Settings, session: Session) -> StructuredQueryService:
    guard_config = settings.sql_guard_config()
    guard = SQLGuard(allowed_functions=guard_config.allowed_functions, max_limit=_MAX_LIMIT)
    return StructuredQueryService(session=session, settings=settings, guard=guard)


__all__ = [
    "QueryRequest",
    "QueryResult",
    "TableRow",
    "ColumnMeta",
    "SQLGuard",
    "GuardViolation",
    "StructuredQueryService",
    "build_query_service",
]
