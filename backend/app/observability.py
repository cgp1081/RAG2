"""Observability helpers for Prometheus metrics and OpenTelemetry tracing."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI
from prometheus_client import (  # type: ignore
    CollectorRegistry,
    Counter,
    Histogram,
    CONTENT_TYPE_LATEST,
    generate_latest,
)
from structlog import get_logger as structlog_get_logger

from backend.app.config import Settings

try:  # pragma: no cover - optional exporter may be absent in some environments
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
except Exception:  # pragma: no cover - tracing disabled when deps missing
    trace = None  # type: ignore
    OTLPSpanExporter = None  # type: ignore
    FastAPIInstrumentor = None  # type: ignore
    HTTPXClientInstrumentor = None  # type: ignore
    TracerProvider = None  # type: ignore
    BatchSpanProcessor = None  # type: ignore
    ConsoleSpanExporter = None  # type: ignore
    TraceIdRatioBased = None  # type: ignore
    Resource = None  # type: ignore

__all__ = [
    "CollectorRegistry",
    "CONTENT_TYPE_LATEST",
    "HTTPRequestObservation",
    "configure_tracing",
    "generate_latest",
    "get_prometheus_registry",
    "init_metrics",
    "record_http_request",
    "record_ingestion_duration",
    "record_rag_duration",
]


_logger = structlog_get_logger(__name__)
_registry_lock = threading.Lock()
_registry: CollectorRegistry | None = None
_metrics_ready = False
_http_requests_total: Counter | None = None
_http_request_duration_seconds: Histogram | None = None
_ingestion_run_duration_seconds: Histogram | None = None
_rag_pipeline_duration_seconds: Histogram | None = None
_tracing_configured = False


@dataclass(slots=True)
class HTTPRequestObservation:
    method: str
    path: str
    status_code: int
    duration_seconds: float
    tenant_id: str | None = None


def _normalise(value: Optional[str], default: str = "unknown") -> str:
    return value if value else default


def init_metrics(settings: Settings) -> CollectorRegistry | None:
    """Initialise Prometheus metrics once."""

    global _metrics_ready, _registry, _http_requests_total, _http_request_duration_seconds
    global _ingestion_run_duration_seconds, _rag_pipeline_duration_seconds

    config = settings.observability_config()
    if not (config.observability_enabled and config.prometheus_enabled):
        return None

    with _registry_lock:
        if _metrics_ready and _registry is not None:
            return _registry

        registry = CollectorRegistry()

        _http_requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests",
            labelnames=("method", "path", "status_code", "tenant_id"),
            registry=registry,
        )
        _http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds",
            labelnames=("method", "path", "status_code", "tenant_id"),
            registry=registry,
            buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )
        _ingestion_run_duration_seconds = Histogram(
            "ingestion_run_duration_seconds",
            "Document ingestion run duration in seconds",
            labelnames=("tenant_id", "status"),
            registry=registry,
            buckets=(5, 15, 30, 60, 120, 300, 600, 1200),
        )
        _rag_pipeline_duration_seconds = Histogram(
            "rag_pipeline_duration_seconds",
            "RAG pipeline execution latency in seconds",
            labelnames=("tenant_id", "outcome"),
            registry=registry,
            buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )

        _registry = registry
        _metrics_ready = True
        _logger.info("observability.prometheus.initialised", port=config.prometheus_port)
        return registry


def get_prometheus_registry() -> CollectorRegistry | None:
    """Return the configured registry if metrics are enabled."""

    return _registry if _metrics_ready else None


def record_http_request(observation: HTTPRequestObservation) -> None:
    """Record HTTP metrics when Prometheus is active."""

    if _http_requests_total is None or _http_request_duration_seconds is None:
        return

    labels = dict(
        method=observation.method,
        path=observation.path,
        status_code=str(observation.status_code),
        tenant_id=_normalise(observation.tenant_id),
    )
    _http_requests_total.labels(**labels).inc()
    _http_request_duration_seconds.labels(**labels).observe(observation.duration_seconds)


def record_ingestion_duration(
    *,
    tenant_id: str | None,
    status: str,
    duration_seconds: float,
) -> None:
    """Record ingestion run durations when metrics are active."""

    if _ingestion_run_duration_seconds is None:
        return

    _ingestion_run_duration_seconds.labels(
        tenant_id=_normalise(tenant_id),
        status=_normalise(status, "unknown"),
    ).observe(duration_seconds)


def record_rag_duration(
    *,
    tenant_id: str | None,
    outcome: str,
    duration_seconds: float,
) -> None:
    """Record RAG pipeline timing metrics when enabled."""

    if _rag_pipeline_duration_seconds is None:
        return

    _rag_pipeline_duration_seconds.labels(
        tenant_id=_normalise(tenant_id),
        outcome=_normalise(outcome, "unknown"),
    ).observe(duration_seconds)


def configure_tracing(settings: Settings, app: FastAPI) -> bool:
    """Configure OpenTelemetry tracing if enabled in settings."""

    global _tracing_configured

    config = settings.observability_config()
    if not (config.observability_enabled and config.otel_enabled):
        return False

    telemetry_unavailable = (
        trace is None
        or TracerProvider is None
        or BatchSpanProcessor is None
        or TraceIdRatioBased is None
    )
    if telemetry_unavailable:
        _logger.warning(
            "observability.tracing.unavailable",
            reason="opentelemetry not installed",
        )
        return False

    if _tracing_configured:
        return True

    resource = Resource.create({"service.name": "rag-backend"}) if Resource else None
    tracer_provider = TracerProvider(
        sampler=TraceIdRatioBased(config.trace_sample_rate),
        resource=resource,
    )

    exporter = None
    if config.otel_exporter_otlp_endpoint and OTLPSpanExporter is not None:
        exporter = OTLPSpanExporter(endpoint=str(config.otel_exporter_otlp_endpoint))
    elif ConsoleSpanExporter is not None:
        exporter = ConsoleSpanExporter()

    if exporter is not None:
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(tracer_provider)

    if FastAPIInstrumentor is not None:
        FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)
    if HTTPXClientInstrumentor is not None:
        HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)

    _tracing_configured = True
    _logger.info(
        "observability.tracing.initialised",
        exporter=(exporter.__class__.__name__ if exporter else "console"),
    )
    return True
