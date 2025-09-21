"""Add ingestion pipeline metadata columns.

Revision ID: 0002_ingestion_pipeline
Revises: 0001_initial
Create Date: 2025-09-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_ingestion_pipeline"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Documents
    op.add_column(
        "documents",
        sa.Column("sha256", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "documents",
        sa.Column("content_size", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "documents",
        sa.Column("mime_type", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_documents_tenant_sha",
        "documents",
        ["tenant_id", "sha256"],
        unique=True,
    )
    op.execute("ALTER TABLE documents ALTER COLUMN sha256 DROP DEFAULT")
    op.execute("ALTER TABLE documents ALTER COLUMN content_size DROP DEFAULT")

    # Document chunks
    op.add_column(
        "document_chunks",
        sa.Column("sha256", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "document_chunks",
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("document_chunks", "chunk_index", new_column_name="chunk_order")
    op.create_unique_constraint(
        "uq_document_chunk_order",
        "document_chunks",
        ["document_id", "chunk_order"],
    )
    op.execute("ALTER TABLE document_chunks ALTER COLUMN sha256 DROP DEFAULT")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN token_count DROP DEFAULT")

    # Ingestion runs
    op.add_column(
        "ingestion_runs",
        sa.Column("path", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("total_documents", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("processed_documents", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute("ALTER TABLE ingestion_runs ALTER COLUMN total_documents DROP DEFAULT")
    op.execute("ALTER TABLE ingestion_runs ALTER COLUMN processed_documents DROP DEFAULT")


def downgrade() -> None:
    op.execute("ALTER TABLE ingestion_runs ALTER COLUMN processed_documents SET DEFAULT 0")
    op.execute("ALTER TABLE ingestion_runs ALTER COLUMN total_documents SET DEFAULT 0")
    op.drop_column("ingestion_runs", "processed_documents")
    op.drop_column("ingestion_runs", "total_documents")
    op.drop_column("ingestion_runs", "path")

    op.execute("ALTER TABLE document_chunks ALTER COLUMN token_count SET DEFAULT 0")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN sha256 SET DEFAULT ''")
    op.drop_constraint("uq_document_chunk_order", "document_chunks", type_="unique")
    op.alter_column("document_chunks", "chunk_order", new_column_name="chunk_index")
    op.drop_column("document_chunks", "token_count")
    op.drop_column("document_chunks", "sha256")

    op.execute("ALTER TABLE documents ALTER COLUMN content_size SET DEFAULT 0")
    op.execute("ALTER TABLE documents ALTER COLUMN sha256 SET DEFAULT ''")
    op.drop_index("ix_documents_tenant_sha", table_name="documents")
    op.drop_column("documents", "mime_type")
    op.drop_column("documents", "content_size")
    op.drop_column("documents", "sha256")
