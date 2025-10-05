from __future__ import annotations

from alembic import command
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
            "chunk_order",
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
            "path",
            "total_documents",
            "processed_documents",
        },
        "ingestion_events": {"id", "run_id", "event_type", "payload", "created_at"},
        "structured_tables": {
            "id",
            "tenant_id",
            "table_name",
            "display_name",
            "source_path",
            "version",
            "row_count",
            "ingested_at",
            "schema_hash",
            "status",
            "error",
            "created_at",
            "updated_at",
        },
        "structured_columns": {
            "id",
            "table_id",
            "column_order",
            "name",
            "slug",
            "data_type",
            "is_primary_key",
            "nullable",
            "sample_values",
            "stats",
            "created_at",
            "updated_at",
        },
        "structured_rows": {
            "id",
            "table_id",
            "row_index",
            "payload",
            "created_at",
        },
        "structured_query_logs": {
            "id",
            "tenant_id",
            "table_id",
            "executed_sql",
            "parameters",
            "status",
            "reason",
            "row_count",
            "duration_ms",
            "created_at",
        },
        "call_sessions": {
            "id",
            "tenant_id",
            "twilio_call_sid",
            "status",
            "caller_number",
            "callee_number",
            "confidence",
            "transcript",
            "summary",
            "recording_url",
            "storage_object_key",
            "caller_metadata",
            "avg_turn_latency_ms",
            "error",
            "created_at",
            "updated_at",
            "ended_at",
            "escalated",
        },
        "call_turns": {
            "id",
            "session_id",
            "sequence",
            "speaker",
            "text",
            "confidence",
            "started_at",
            "ended_at",
        },
        "call_recordings": {
            "id",
            "session_id",
            "media_uri",
            "content_type",
            "duration_seconds",
            "storage_path",
            "created_at",
        },
        "call_metrics_daily": {
            "id",
            "tenant_id",
            "date",
            "total_calls",
            "escalations",
            "avg_confidence",
            "avg_handle_seconds",
            "created_at",
        },
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


def test_call_analytics_columns_removed_on_downgrade(alembic_config, db_engine):
    command.downgrade(alembic_config, "0004_voice_sessions")
    try:
        with db_engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'call_sessions'
                    """
                )
            )
            columns = {row.column_name for row in result}
            assert "summary" not in columns
            assert "call_metrics_daily" not in {
                row.table_name
                for row in conn.execute(
                    text(
                        """
                        SELECT table_name FROM information_schema.tables
                        WHERE table_schema = 'public'
                        """
                    )
                )
            }
    finally:
        command.upgrade(alembic_config, "head")
