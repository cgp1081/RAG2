"""Admin APIs for reviewing telephony call analytics."""
from __future__ import annotations

from datetime import date, datetime
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.config import Settings, settings_dependency
from backend.app.routers.ingestion import require_admin_api_key
from backend.app.schemas.calls import (
    CallDetailSchema,
    CallSummarySchema,
    CallTurnSchema,
    DailyMetricSchema,
    PaginatedCallsSchema,
)
from backend.db.models import CallMetricsDaily, CallSession, CallTurn, Tenant
from backend.db.session import SessionLocal
from backend.voice.storage import build_call_storage_adapter

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/calls", tags=["admin:calls"])


def _get_db_session() -> Session:
    with SessionLocal() as session:
        yield session


def _resolve_tenant_id(db: Session, tenant_slug_or_id: Optional[str]) -> Optional[uuid.UUID]:
    if tenant_slug_or_id is None:
        return None
    try:
        return uuid.UUID(tenant_slug_or_id)
    except ValueError:
        tenant = db.execute(select(Tenant).where(Tenant.slug == tenant_slug_or_id)).scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        return tenant.id


@router.get("", dependencies=[Depends(require_admin_api_key)])
def list_calls(
    *,
    tenant: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    escalated: Optional[bool] = Query(None),
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    settings: Settings = Depends(settings_dependency),
    db_session: Session = Depends(_get_db_session),
) -> PaginatedCallsSchema:
    tenant_uuid = _resolve_tenant_id(db_session, tenant)

    conditions = []
    if tenant_uuid:
        conditions.append(CallSession.tenant_id == tenant_uuid)
    if status_filter:
        conditions.append(CallSession.status == status_filter)
    if escalated is not None:
        conditions.append(CallSession.escalated.is_(escalated))
    if date_from:
        conditions.append(func.date(CallSession.created_at) >= date_from)
    if date_to:
        conditions.append(func.date(CallSession.created_at) <= date_to)

    base_query = select(CallSession)
    if conditions:
        base_query = base_query.where(*conditions)

    count_query = select(func.count()).select_from(CallSession)
    if conditions:
        count_query = count_query.where(*conditions)

    total = db_session.execute(count_query).scalar_one()
    items = (
        db_session.execute(
            base_query.order_by(CallSession.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        .scalars()
        .all()
    )

    storage_adapter = build_call_storage_adapter(settings)
    summaries: list[CallSummarySchema] = []
    for call in items:
        handle_seconds = None
        if call.ended_at and call.created_at:
            handle_seconds = (call.ended_at - call.created_at).total_seconds()
        transcript_preview = call.summary
        if not transcript_preview and call.transcript:
            transcript_preview = (
                call.transcript[:200] + "..." if len(call.transcript) > 200 else call.transcript
            )
        summaries.append(
            CallSummarySchema(
                id=str(call.id),
                tenant_id=str(call.tenant_id),
                caller_number=call.caller_number,
                status=call.status,
                confidence=call.confidence,
                escalated=bool(call.escalated),
                started_at=call.created_at,
                ended_at=call.ended_at,
                handle_seconds=handle_seconds,
                recording_url=call.recording_url or (
                    storage_adapter.presign(call.storage_object_key) if call.storage_object_key else None
                ),
                transcript_preview=transcript_preview,
            )
        )

    logger.info(
        "admin.calls.list",
        tenant=tenant,
        page=page,
        page_size=page_size,
        total=total,
    )

    return PaginatedCallsSchema(
        items=summaries,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{call_id}", dependencies=[Depends(require_admin_api_key)])
def get_call_detail(
    call_id: str,
    settings: Settings = Depends(settings_dependency),
    db_session: Session = Depends(_get_db_session),
) -> CallDetailSchema:
    try:
        call_uuid = uuid.UUID(call_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid call_id") from exc

    call = db_session.get(CallSession, call_uuid)
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call session not found")

    turns = (
        db_session.execute(
            select(CallTurn).where(CallTurn.session_id == call_uuid).order_by(CallTurn.sequence)
        )
        .scalars()
        .all()
    )

    turn_payloads = [
        CallTurnSchema(
            sequence=turn.sequence,
            speaker=turn.speaker,
            text=turn.text,
            confidence=turn.confidence,
            started_at=turn.started_at,
            ended_at=turn.ended_at,
        )
        for turn in turns
    ]

    handle_seconds = None
    if call.ended_at and call.created_at:
        handle_seconds = (call.ended_at - call.created_at).total_seconds()

    storage_adapter = build_call_storage_adapter(settings)
    recording_url = call.recording_url or (storage_adapter.presign(call.storage_object_key) if call.storage_object_key else None)

    summary = call.summary
    if not summary and call.transcript:
        summary = call.transcript[:200] + "..." if len(call.transcript) > 200 else call.transcript

    logger.info("admin.calls.detail", call_session_id=str(call.id), tenant_id=str(call.tenant_id))

    return CallDetailSchema(
        id=str(call.id),
        tenant_id=str(call.tenant_id),
        caller_number=call.caller_number,
        status=call.status,
        confidence=call.confidence,
        escalated=bool(call.escalated),
        started_at=call.created_at,
        ended_at=call.ended_at,
        handle_seconds=handle_seconds,
        recording_url=recording_url,
        transcript_preview=summary,
        transcript=call.transcript,
        turns=turn_payloads,
        caller_metadata=call.caller_metadata,
        storage_object_key=call.storage_object_key,
    )


@router.get("/metrics/daily", dependencies=[Depends(require_admin_api_key)])
def get_daily_metrics(
    *,
    tenant: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    db_session: Session = Depends(_get_db_session),
) -> list[DailyMetricSchema]:
    query = select(CallMetricsDaily)
    if tenant:
        tenant_obj = db_session.execute(select(Tenant).where(Tenant.slug == tenant)).scalar_one_or_none()
        if tenant_obj is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        query = query.where(CallMetricsDaily.tenant_id == tenant_obj.id)
    if date_from:
        query = query.where(CallMetricsDaily.date >= date_from)
    if date_to:
        query = query.where(CallMetricsDaily.date <= date_to)
    query = query.order_by(CallMetricsDaily.date.desc())

    rows = db_session.execute(query).scalars().all()
    logger.info("admin.calls.metrics", tenant=tenant, count=len(rows))
    return [
        DailyMetricSchema(
            tenant_id=str(row.tenant_id),
            date=row.date,
            total_calls=row.total_calls,
            escalations=row.escalations,
            avg_confidence=float(row.avg_confidence) if row.avg_confidence is not None else None,
            avg_handle_seconds=float(row.avg_handle_seconds) if row.avg_handle_seconds is not None else None,
        )
        for row in rows
    ]


__all__ = ["router"]
