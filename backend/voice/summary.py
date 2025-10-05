"""Utilities for computing daily call metrics."""
from __future__ import annotations

from datetime import date
from typing import Optional

import structlog
from sqlalchemy import case, delete, func, select

from backend.db.models import CallMetricsDaily, CallSession
from backend.db.session import SessionLocal

logger = structlog.get_logger(__name__)


async def compute_daily_metrics(start: Optional[date] = None, end: Optional[date] = None) -> int:
    """Aggregate completed calls per tenant/date and update call_metrics_daily."""

    with SessionLocal() as session:
        if start is None:
            start = session.execute(
                select(func.min(func.date(CallSession.created_at)))
            ).scalar()
            if start is None:
                logger.info("voice.summary.no_calls")
                return 0
        if end is None:
            end = date.today()
        if end < start:
            start, end = end, start

        date_filter = func.date(CallSession.created_at)
        query_conditions = [CallSession.status == "completed"]
        query_conditions.append(date_filter >= start)
        query_conditions.append(date_filter <= end)

        aggregation = (
            select(
                CallSession.tenant_id,
                date_filter.label("session_date"),
                func.count().label("total_calls"),
                func.sum(case((CallSession.escalated.is_(True), 1), else_=0)).label("escalations"),
                func.avg(CallSession.confidence).label("avg_confidence"),
                func.avg(
                    func.extract(
                        "epoch",
                        CallSession.ended_at - CallSession.created_at,
                    )
                ).label("avg_handle_seconds"),
            )
            .where(*query_conditions)
            .group_by(CallSession.tenant_id, "session_date")
        )

        metrics = session.execute(aggregation).all()

        session.execute(
            delete(CallMetricsDaily).where(
                CallMetricsDaily.date >= start,
                CallMetricsDaily.date <= end,
            )
        )

        for tenant_id, session_date, total_calls, escalations, avg_confidence, avg_handle_seconds in metrics:
            session.add(
                CallMetricsDaily(
                    tenant_id=tenant_id,
                    date=session_date,
                    total_calls=int(total_calls or 0),
                    escalations=int(escalations or 0),
                    avg_confidence=float(avg_confidence) if avg_confidence is not None else None,
                    avg_handle_seconds=float(avg_handle_seconds) if avg_handle_seconds is not None else None,
                )
            )

        session.commit()
        logger.info(
            "voice.summary.updated",
            start=str(start),
            end=str(end),
            rows=len(metrics),
        )
        return len(metrics)


__all__ = ["compute_daily_metrics"]
