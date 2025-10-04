"""Create structured data tables for CSV ingestion.

Revision ID: 0003_structured_tables
Revises: 0002_ingestion_pipeline
Create Date: 2025-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_structured_tables"
down_revision = "0002_ingestion_pipeline"
branch_labels = None
depends_on = None

_UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "structured_tables",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("source_path", sa.String(length=1024), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ingested_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("schema_hash", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'processing'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_structured_tables_tenant", "structured_tables", ["tenant_id"])
    op.create_unique_constraint(
        "uq_structured_tables_version",
        "structured_tables",
        ["tenant_id", "table_name", "version"],
    )

    op.create_table(
        "structured_columns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT),
        sa.Column(
            "table_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("structured_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("column_order", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("data_type", sa.String(length=50), nullable=False),
        sa.Column("is_primary_key", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("nullable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sample_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_structured_columns_table_name",
        "structured_columns",
        ["table_id", "name"],
    )

    op.create_table(
        "structured_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT),
        sa.Column(
            "table_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("structured_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_structured_rows_table_row_index",
        "structured_rows",
        ["table_id", "row_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_structured_rows_table_row_index", table_name="structured_rows")
    op.drop_table("structured_rows")

    op.drop_index("ix_structured_columns_table_name", table_name="structured_columns")
    op.drop_table("structured_columns")

    op.drop_constraint("uq_structured_tables_version", "structured_tables", type_="unique")
    op.drop_index("ix_structured_tables_tenant", table_name="structured_tables")
    op.drop_table("structured_tables")
