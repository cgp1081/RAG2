"""Structured data ingestion pipeline for CSV inputs."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.logging import get_logger
from backend.db.models import StructuredColumn, StructuredRow, StructuredTable
from backend.structured.schema_inference import ColumnDefinition, infer_schema

_CHUNK_SIZE = 10_000
_SAMPLE_ROW_LIMIT = 50_000


class StructuredTableIngestion:
    """Coordinate ingestion of structured CSV files into relational storage.

    TODO: integrate scheduler/connector orchestration once structured sources are
    plumbed through the PRD's connector catalog.
    """

    def __init__(self) -> None:
        self._logger = get_logger(__name__)

    async def ingest_csv(
        self,
        path: Path,
        table_name: str,
        tenant_id: uuid.UUID,
        *,
        settings: Settings,
        session: Session,
        max_rows: int | None = None,
        sample_size: int | None = None,
    ) -> StructuredTable:
        config = settings.structured_config()
        resolved_max_rows = max_rows or config.max_rows
        resolved_sample_size = sample_size or config.sample_size
        sample_limit = min(resolved_max_rows, _SAMPLE_ROW_LIMIT)

        csv_path = Path(path)
        if not csv_path.exists() or not csv_path.is_file():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        if csv_path.stat().st_size == 0:
            raise ValueError("CSV file is empty")

        next_version = self._resolve_next_version(session, tenant_id, table_name)
        structured_table = StructuredTable(
            tenant_id=tenant_id,
            table_name=table_name,
            display_name=table_name,
            source_path=str(csv_path.resolve()),
            version=next_version,
            status="processing",
            row_count=0,
        )
        session.add(structured_table)
        session.flush()

        self._logger.info(
            "structured.ingest.started",
            tenant_id=str(tenant_id),
            table_id=str(structured_table.id),
            table_name=table_name,
            version=next_version,
        )

        total_rows = 0
        sample_frames: list[pd.DataFrame] = []
        row_batches: list[dict] = []
        row_index = 0

        try:
            for chunk in pd.read_csv(csv_path, chunksize=_CHUNK_SIZE):
                rows_in_chunk = len(chunk.index)
                if total_rows + rows_in_chunk > resolved_max_rows:
                    raise ValueError(
                        f"CSV exceeds allowed row count ({resolved_max_rows})."
                    )

                if total_rows < sample_limit:
                    remaining = sample_limit - total_rows
                    if remaining >= rows_in_chunk:
                        sample_frames.append(chunk)
                    else:
                        sample_frames.append(chunk.head(remaining))

                payloads = _chunk_to_payloads(chunk)
                for payload in payloads:
                    row_batches.append(
                        {
                            "table_id": structured_table.id,
                            "row_index": row_index,
                            "payload": payload,
                        }
                    )
                    row_index += 1

                total_rows += rows_in_chunk

                if row_batches:
                    session.execute(sa.insert(StructuredRow), row_batches)
                    session.commit()
                    row_batches.clear()

            if total_rows == 0:
                raise ValueError("CSV contains no rows")

            inference_frame = pd.concat(sample_frames, ignore_index=True) if sample_frames else pd.DataFrame()
            column_defs = infer_schema(inference_frame, sample_size=resolved_sample_size)
            _persist_columns(session, structured_table, column_defs)

            structured_table.row_count = total_rows
            structured_table.status = "ready"
            structured_table.ingested_at = datetime.now(timezone.utc)
            structured_table.schema_hash = _schema_hash(column_defs)
            session.commit()

            self._logger.info(
                "structured.ingest.completed",
                tenant_id=str(tenant_id),
                table_id=str(structured_table.id),
                table_name=table_name,
                version=structured_table.version,
                rows=total_rows,
                column_count=len(column_defs),
            )

            return structured_table
        except Exception as exc:
            session.rollback()
            structured_table.status = "failed"
            structured_table.error = str(exc)
            session.add(structured_table)
            session.commit()
            self._logger.error(
                "structured.ingest.failed",
                tenant_id=str(tenant_id),
                table_id=str(structured_table.id),
                table_name=table_name,
                error=str(exc),
            )
            raise

    def _resolve_next_version(self, session: Session, tenant_id: uuid.UUID, table_name: str) -> int:
        result = (
            session.query(sa.func.max(StructuredTable.version))
            .filter(StructuredTable.tenant_id == tenant_id)
            .filter(StructuredTable.table_name == table_name)
            .scalar()
        )
        return int(result or 0) + 1


def _chunk_to_payloads(chunk: pd.DataFrame) -> Iterable[dict]:
    records = chunk.where(pd.notnull(chunk), None).to_dict(orient="records")
    return records


def _persist_columns(
    session: Session,
    table: StructuredTable,
    columns: list[ColumnDefinition],
) -> None:
    if not columns:
        return

    payloads = []
    for order, column in enumerate(columns, start=1):
        payloads.append(
            {
                "table_id": table.id,
                "column_order": order,
                "name": column.name,
                "slug": column.slug,
                "data_type": column.data_type,
                "is_primary_key": column.is_primary_key,
                "nullable": column.nullable,
                "sample_values": column.sample_values,
                "stats": column.stats,
            }
        )

    session.execute(sa.insert(StructuredColumn), payloads)
    session.flush()


def _schema_hash(columns: list[ColumnDefinition]) -> str | None:
    if not columns:
        return None
    serialisable = [
        {
            "name": column.name,
            "slug": column.slug,
            "data_type": column.data_type,
            "nullable": column.nullable,
            "is_primary_key": column.is_primary_key,
        }
        for column in columns
    ]
    payload = json.dumps(serialisable, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = ["StructuredTableIngestion"]
