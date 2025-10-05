"""ORM models for the RAG backend persistence layer."""
from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

_UUID_SERVER_DEFAULT = sa.text("gen_random_uuid()")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    slug: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    sources: Mapped[list["Source"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    ingestion_runs: Mapped[list["IngestionRun"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    structured_tables: Mapped[list["StructuredTable"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    structured_query_logs: Mapped[list["StructuredQueryLog"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    call_sessions: Mapped[list["CallSession"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    call_metrics: Mapped[list["CallMetricsDaily"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        server_default=sa.text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    tenant: Mapped[Tenant] = relationship(back_populates="sources", lazy="selectin")
    documents: Mapped[list["Document"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    ingestion_runs: Mapped[list["IngestionRun"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "source_id", "external_id", name="uq_documents_external"
        ),
        sa.Index("ix_documents_tenant_id", "tenant_id"),
        sa.Index("ix_documents_source_id", "source_id"),
        sa.Index("ix_documents_tenant_sha", "tenant_id", "sha256", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    external_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        default="pending",
        server_default=sa.text("'pending'"),
    )
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    content_size: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    mime_type: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    tenant: Mapped[Tenant] = relationship(back_populates="documents", lazy="selectin")
    source: Mapped[Source | None] = relationship(back_populates="documents", lazy="selectin")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DocumentChunk.chunk_order",
    )



class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        sa.Index("ix_document_chunks_document_id", "document_id"),
        sa.UniqueConstraint("document_id", "chunk_order", name="uq_document_chunk_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_order: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    embedding: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="TODO: replace JSON placeholder with vector column when available",
    )
    sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    document: Mapped[Document] = relationship(back_populates="chunks", lazy="selectin")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        sa.Index("ix_ingestion_runs_tenant_id", "tenant_id"),
        sa.Index("ix_ingestion_runs_source_id", "source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    path: Mapped[str | None] = mapped_column(sa.String(1024), nullable=True)
    total_documents: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    processed_documents: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    tenant: Mapped[Tenant] = relationship(back_populates="ingestion_runs", lazy="selectin")
    source: Mapped[Source | None] = relationship(back_populates="ingestion_runs", lazy="selectin")
    events: Mapped[list["IngestionEvent"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class IngestionEvent(Base):
    __tablename__ = "ingestion_events"
    __table_args__ = (
        sa.Index("ix_ingestion_events_run_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    run: Mapped[IngestionRun] = relationship(back_populates="events", lazy="selectin")


class StructuredTable(Base):
    __tablename__ = "structured_tables"
    __table_args__ = (
        sa.Index("ix_structured_tables_tenant", "tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "table_name", "version", name="uq_structured_tables_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    source_path: Mapped[str] = mapped_column(sa.String(1024), nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    row_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    ingested_at: Mapped[datetime | None] = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    schema_hash: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="processing")
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    tenant: Mapped[Tenant] = relationship(back_populates="structured_tables", lazy="selectin")
    columns: Mapped[list["StructuredColumn"]] = relationship(
        back_populates="table",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="StructuredColumn.column_order",
    )
    rows: Mapped[list["StructuredRow"]] = relationship(
        back_populates="table",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="StructuredRow.row_index",
    )
    query_logs: Mapped[list["StructuredQueryLog"]] = relationship(
        back_populates="table",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class StructuredColumn(Base):
    __tablename__ = "structured_columns"
    __table_args__ = (
        sa.Index("ix_structured_columns_table_name", "table_id", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("structured_tables.id", ondelete="CASCADE"),
        nullable=False,
    )
    column_order: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    slug: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    is_primary_key: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    nullable: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    sample_values: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    table: Mapped[StructuredTable] = relationship(back_populates="columns", lazy="selectin")


class StructuredRow(Base):
    __tablename__ = "structured_rows"
    __table_args__ = (
        sa.Index("ix_structured_rows_table_row_index", "table_id", "row_index", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("structured_tables.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    table: Mapped[StructuredTable] = relationship(back_populates="rows", lazy="selectin")


class StructuredQueryLog(Base):
    __tablename__ = "structured_query_logs"
    __table_args__ = (
        sa.Index("ix_structured_query_logs_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("structured_tables.id", ondelete="SET NULL"),
        nullable=True,
    )
    executed_sql: Mapped[str] = mapped_column(sa.Text, nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    tenant: Mapped[Tenant] = relationship(back_populates="structured_query_logs", lazy="selectin")
    table: Mapped[StructuredTable | None] = relationship(back_populates="query_logs", lazy="selectin")


class CallSession(Base):
    __tablename__ = "call_sessions"
    __table_args__ = (
        sa.Index("ix_call_sessions_tenant_escalated", "tenant_id", "escalated"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    twilio_call_sid: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        sa.Enum(
            "initiated",
            "running",
            "completed",
            "failed",
            name="call_session_status",
        ),
        nullable=False,
        default="initiated",
        server_default="initiated",
    )
    caller_number: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    callee_number: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    transcript: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    storage_object_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    caller_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    avg_turn_latency_ms: Mapped[float | None] = mapped_column(sa.Numeric(10, 2), nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    escalated: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=True,
    )

    tenant: Mapped[Tenant] = relationship(back_populates="call_sessions", lazy="selectin")
    turns: Mapped[list["CallTurn"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CallTurn.sequence",
    )
    recordings: Mapped[list["CallRecording"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CallTurn(Base):
    __tablename__ = "call_turns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("call_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(
        sa.Enum("caller", "assistant", name="call_turn_speaker"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=True,
    )

    session: Mapped[CallSession] = relationship(back_populates="turns", lazy="selectin")


class CallRecording(Base):
    __tablename__ = "call_recordings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("call_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    media_uri: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    session: Mapped[CallSession] = relationship(back_populates="recordings", lazy="selectin")


class CallMetricsDaily(Base):
    __tablename__ = "call_metrics_daily"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "date", name="uq_call_metrics_daily_tenant_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_SERVER_DEFAULT,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    total_calls: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    escalations: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    avg_confidence: Mapped[float | None] = mapped_column(sa.Numeric(5, 2), nullable=True)
    avg_handle_seconds: Mapped[float | None] = mapped_column(sa.Numeric(10, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    tenant: Mapped[Tenant] = relationship(back_populates="call_metrics", lazy="selectin")


class IngestionEventType:
    """Canonical ingestion event types."""

    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    DOCUMENT_STARTED = "document_started"
    DOCUMENT_SKIPPED = "document_skipped"
    DOCUMENT_COMPLETED = "document_completed"
    CHUNK_SKIPPED_DUPLICATE = "chunk_skipped_duplicate"
    ERROR = "error"


__all__ = [
    "Tenant",
    "Source",
    "Document",
    "DocumentChunk",
    "IngestionRun",
    "IngestionEvent",
    "IngestionEventType",
    "StructuredTable",
    "StructuredColumn",
    "StructuredRow",
    "StructuredQueryLog",
    "CallSession",
    "CallTurn",
    "CallRecording",
    "CallMetricsDaily",
]
