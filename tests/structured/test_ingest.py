from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pandas import DataFrame

from backend.app.config import Settings
from backend.db.models import StructuredColumn, StructuredRow, StructuredTable, Tenant
from backend.structured.ingest import StructuredTableIngestion
from backend.structured.schema_inference import infer_schema


@pytest.mark.asyncio
async def test_ingest_table_creates_metadata_and_rows(db_session, settings_override: Settings, tmp_path: Path):
    tenant = Tenant(name="Acme Corp", slug="default")
    db_session.add(tenant)
    db_session.commit()

    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("id,name,active\n1,Alice,true\n2,Bob,false\n3,Charlie,true\n", encoding="utf-8")

    pipeline = StructuredTableIngestion()
    table = await pipeline.ingest_csv(
        path=csv_path,
        table_name="employees",
        tenant_id=tenant.id,
        settings=settings_override,
        session=db_session,
    )

    db_session.refresh(table)

    assert table.row_count == 3
    assert table.status == "ready"
    columns = (
        db_session.query(StructuredColumn)
        .filter(StructuredColumn.table_id == table.id)
        .order_by(StructuredColumn.column_order)
        .all()
    )
    assert len(columns) == 3
    assert any(column.is_primary_key for column in columns)
    for column in columns:
        if column.sample_values:
            assert len(column.sample_values) <= settings_override.structured_sample_size

    rows = db_session.query(StructuredRow).filter(StructuredRow.table_id == table.id).all()
    assert len(rows) == 3
    assert rows[0].payload["name"] == "Alice"


@pytest.mark.asyncio
async def test_ingest_table_invalid_csv_marks_failure(db_session, settings_override: Settings, tmp_path: Path):
    tenant = Tenant(name="Broken Corp", slug="broken")
    db_session.add(tenant)
    db_session.commit()

    csv_path = tmp_path / "broken.csv"
    csv_path.write_text("bad,data\n1\n2\n", encoding="utf-8")

    pipeline = StructuredTableIngestion()

    with pytest.raises(Exception):
        await pipeline.ingest_csv(
            path=csv_path,
            table_name="broken_table",
            tenant_id=tenant.id,
            settings=settings_override,
            session=db_session,
        )

    table = (
        db_session.query(StructuredTable)
        .filter(StructuredTable.tenant_id == tenant.id, StructuredTable.table_name == "broken_table")
        .one()
    )
    assert table.status == "failed"
    assert table.error is not None


def test_infer_schema_detects_primary_key_and_stats():
    df: DataFrame = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "name": ["Alice", "Bob", "Charlie", None],
            "created_at": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        }
    )

    columns = infer_schema(df, sample_size=2)
    assert len(columns) == 3

    id_column = next(column for column in columns if column.name == "id")
    assert id_column.is_primary_key
    assert id_column.data_type == "integer"

    name_column = next(column for column in columns if column.name == "name")
    assert name_column.nullable is True
    assert "null_ratio" in name_column.stats
    assert name_column.stats["null_ratio"] > 0

    timestamp_column = next(column for column in columns if column.name == "created_at")
    assert len(timestamp_column.sample_values) <= 2
