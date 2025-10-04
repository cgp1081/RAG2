"""FastAPI dependencies for structured query services."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.config import Settings, settings_dependency
from backend.db.session import get_db_session
from backend.structured.query_service import StructuredQueryService, build_query_service


def get_structured_query_service(
    settings: Settings = Depends(settings_dependency),
    session: Session = Depends(get_db_session),
) -> StructuredQueryService:
    """Provide a request-scoped structured query service."""

    return build_query_service(settings, session)


__all__ = ["get_structured_query_service"]
