"""Admin ingestion status endpoints."""
from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.config import Settings, settings_dependency
from backend.app.logging import get_logger
from backend.app.schemas.ingestion import (
    DocumentStatus,
    IngestionRunSummary,
    PaginatedDocuments,
    PaginatedIngestionRuns,
)
from backend.db.models import Document, DocumentChunk, IngestionRun, Source, Tenant
from backend.db.session import get_db_session

_logger = get_logger(__name__)


def require_admin_api_key(
    api_key: str | None = Header(default=None, alias="X-Admin-API-Key"),
    settings: Settings = Depends(settings_dependency),
) -> None:
    """Guard admin routes with a static API key.

    TODO: replace with tenant-aware authentication once operator console ships.
    """

    configured_key = settings.admin_api_key
    if configured_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is not configured",
        )
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Admin-API-Key header required",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if api_key != configured_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin_api_key)])


def _resolve_tenant(session: Session, tenant_identifier: str) -> Tenant:
    stmt = select(Tenant).where(Tenant.slug == tenant_identifier)
    tenant = session.execute(stmt).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


def _paginate(page: int, page_size: int) -> tuple[int, int]:
    return max(page - 1, 0) * page_size, page_size


@router.get("/ingestion-runs", response_model=PaginatedIngestionRuns)
async def list_ingestion_runs(
    *,
    tenant: str = Query(..., description="Tenant slug"),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    session: Session = Depends(get_db_session),
) -> PaginatedIngestionRuns:
    tenant_obj = _resolve_tenant(session, tenant)

    filters = [IngestionRun.tenant_id == tenant_obj.id]
    if status_filter:
        filters.append(IngestionRun.status == status_filter)

    offset, limit = _paginate(page, page_size)

    total_stmt = select(func.count()).select_from(IngestionRun).where(*filters)
    total = session.execute(total_stmt).scalar_one()

    runs_stmt = (
        select(IngestionRun)
        .where(*filters)
        .options(selectinload(IngestionRun.source))
        .order_by(
            sa.desc(IngestionRun.started_at).nullslast(),
            sa.desc(IngestionRun.created_at),
        )
        .offset(offset)
        .limit(limit)
    )
    runs = session.execute(runs_stmt).scalars().all()

    items = [
        IngestionRunSummary(
            id=run.id,
            tenant_id=run.tenant_id,
            status=run.status,
            source_id=run.source_id,
            source_name=run.source.name if run.source else None,
            source_type=run.source.source_type if run.source else None,
            path=run.path,
            total_documents=run.total_documents,
            processed_documents=run.processed_documents,
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_seconds=(
                (run.finished_at - run.started_at).total_seconds()
                if run.started_at and run.finished_at
                else None
            ),
            error=run.error,
        )
        for run in runs
    ]

    _logger.info(
        "admin.list_ingestion_runs",
        tenant=tenant,
        total=total,
        page=page,
        page_size=page_size,
    )

    return PaginatedIngestionRuns(items=items, total=total, page=page, page_size=page_size)


@router.get("/documents", response_model=PaginatedDocuments)
async def list_documents(
    *,
    tenant: str = Query(..., description="Tenant slug"),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> PaginatedDocuments:
    tenant_obj = _resolve_tenant(session, tenant)

    filters = [Document.tenant_id == tenant_obj.id]
    if status_filter:
        filters.append(Document.status == status_filter)

    offset, limit = _paginate(page, page_size)

    total_stmt = select(func.count()).select_from(Document).where(*filters)
    total = session.execute(total_stmt).scalar_one()

    chunk_counts = (
        select(
            DocumentChunk.document_id.label("document_id"),
            func.count(DocumentChunk.id).label("chunk_count"),
        )
        .group_by(DocumentChunk.document_id)
        .subquery()
    )

    docs_stmt = (
        select(Document, Source, chunk_counts.c.chunk_count)
        .join(Source, Document.source_id == Source.id, isouter=True)
        .join(chunk_counts, chunk_counts.c.document_id == Document.id, isouter=True)
        .where(*filters)
        .order_by(sa.desc(Document.updated_at))
        .offset(offset)
        .limit(limit)
    )
    rows = session.execute(docs_stmt).all()

    items = []
    for document, source, chunk_count in rows:
        items.append(
            DocumentStatus(
                id=document.id,
                tenant_id=document.tenant_id,
                source_id=document.source_id,
                source_name=source.name if source else None,
                source_type=source.source_type if source else None,
                title=document.title,
                status=document.status,
                chunk_count=chunk_count or 0,
                last_ingested_at=document.updated_at,
                sha256=document.sha256,
                mime_type=document.mime_type,
            )
        )

    _logger.info(
        "admin.list_documents",
        tenant=tenant,
        total=total,
        page=page,
        page_size=page_size,
    )

    return PaginatedDocuments(items=items, total=total, page=page, page_size=page_size)


__all__ = ["router", "require_admin_api_key"]
