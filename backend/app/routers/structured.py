"""Admin endpoints for structured SQL querying."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import Settings, settings_dependency
from backend.app.logging import get_logger
from backend.app.routers.ingestion import require_admin_api_key
from backend.app.schemas.structured import (
    StructuredColumnSchema,
    StructuredQueryRequest,
    StructuredQueryResponse,
)
from backend.db.session import get_db_session
from backend.structured.query_service import GuardViolation, QueryResult, StructuredQueryService, build_query_service

_logger = get_logger(__name__)


router = APIRouter(
    prefix="/structured",
    tags=["structured"],
    dependencies=[Depends(require_admin_api_key)],
)


@router.post("/query", response_model=StructuredQueryResponse)
async def execute_structured_query(
    request: StructuredQueryRequest,
    settings: Settings = Depends(settings_dependency),
    session: Session = Depends(get_db_session),
) -> StructuredQueryResponse:
    service = build_query_service(settings, session)

    try:
        tenant_uuid = uuid.UUID(request.tenant_id)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id") from exc

    try:
        result = service.execute(
            query=request.sql,
            tenant_id=tenant_uuid,
            table_name=request.table_name,
        )
    except GuardViolation as exc:
        _logger.info(
            "structured.query.blocked",
            tenant_id=request.tenant_id,
            table_name=request.table_name,
            reason=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        _logger.error(
            "structured.query.error",
            tenant_id=request.tenant_id,
            table_name=request.table_name,
            error=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to execute query") from exc

    _logger.info(
        "structured.query.api",
        tenant_id=request.tenant_id,
        table_name=result.table_name,
        row_count=result.row_count,
        duration_ms=result.execution_ms,
    )

    response = _to_response(result)
    return response


def _to_response(result: QueryResult) -> StructuredQueryResponse:
    return StructuredQueryResponse(
        columns=[StructuredColumnSchema(name=col.name, data_type=col.data_type) for col in result.columns],
        rows=[row.values for row in result.rows],
        row_count=result.row_count,
        execution_ms=result.execution_ms,
        log_id=str(result.log_id),
    )


__all__ = ["router"]
