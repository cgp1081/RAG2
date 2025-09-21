"""ORM models for the RAG backend persistence layer."""
from __future__ import annotations

import uuid
from datetime import datetime

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
]
