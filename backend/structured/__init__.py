"""Structured ingestion and query utilities."""
from .dependencies import get_structured_query_service
from .ingest import StructuredTableIngestion
from .query_service import (
    ColumnMeta,
    GuardViolation,
    QueryRequest,
    QueryResult,
    SQLGuard,
    StructuredQueryService,
    TableRow,
    build_query_service,
)
from .schema_inference import ColumnDefinition, guess_primary_key, infer_schema

__all__ = [
    "StructuredTableIngestion",
    "ColumnDefinition",
    "infer_schema",
    "guess_primary_key",
    "StructuredQueryService",
    "QueryResult",
    "QueryRequest",
    "TableRow",
    "ColumnMeta",
    "SQLGuard",
    "GuardViolation",
    "build_query_service",
    "get_structured_query_service",
]
