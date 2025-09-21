from __future__ import annotations

from sqlalchemy import text


def test_migration_creates_expected_tables(db_engine):
    expected = {
        "tenants": {"id", "name", "slug", "created_at", "updated_at"},
        "sources": {"id", "tenant_id", "name", "source_type", "config", "created_at", "updated_at"},
        "documents": {
            "id",
            "tenant_id",
            "source_id",
            "external_id",
            "title",
            "status",
            "metadata",
            "created_at",
            "updated_at",
        },
        "document_chunks": {
            "id",
            "document_id",
            "chunk_index",
            "content",
            "embedding",
            "created_at",
            "updated_at",
        },
        "ingestion_runs": {
            "id",
            "tenant_id",
            "source_id",
            "status",
            "started_at",
            "finished_at",
            "error",
            "created_at",
        },
        "ingestion_events": {"id", "run_id", "event_type", "payload", "created_at"},
    }

    with db_engine.connect() as conn:
        for table, columns in expected.items():
            result = conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = :table
                    """
                ),
                {"table": table},
            )
            found = {row.column_name for row in result}
            assert columns.issubset(found), f"Missing columns for {table}: {columns - found}"
