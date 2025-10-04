from __future__ import annotations

import pytest
from fastapi import FastAPI

from backend.app import observability
from backend.app.config import Settings
from backend.app.observability import configure_tracing


@pytest.mark.parametrize(
    "exporter_endpoint",
    ["http://collector:4318", None],
)
def test_configure_tracing_instruments(monkeypatch: pytest.MonkeyPatch, test_settings: Settings, exporter_endpoint: str | None) -> None:
    observability._tracing_configured = False  # type: ignore[attr-defined]
    calls: dict[str, object] = {}

    class DummyTrace:
        def set_tracer_provider(self, provider):  # type: ignore[no-untyped-def]
            calls["set_provider"] = provider

    class DummyExporter:
        def __init__(self, endpoint=None):  # type: ignore[no-untyped-def]
            calls["exporter"] = endpoint

        def export(self, spans):  # type: ignore[no-untyped-def]
            return 0

        def shutdown(self):  # type: ignore[no-untyped-def]
            return None

    class DummyBatchSpanProcessor:
        def __init__(self, exporter):  # type: ignore[no-untyped-def]
            calls["processor_exporter"] = exporter

    class DummyTracerProvider:
        def __init__(self, sampler=None, resource=None):  # type: ignore[no-untyped-def]
            calls["sampler"] = sampler
            self._processors = []

        def add_span_processor(self, processor):  # type: ignore[no-untyped-def]
            self._processors.append(processor)
            calls["added_processor"] = processor

    class DummySampler:
        def __init__(self, ratio):  # type: ignore[no-untyped-def]
            calls["sample_rate"] = ratio

    class DummyFastAPIInstrumentor:
        @staticmethod
        def instrument_app(app, tracer_provider=None):  # type: ignore[no-untyped-def]
            calls["fastapi_instrumented"] = tracer_provider

    class DummyHTTPXInstrumentor:
        def instrument(self, tracer_provider=None):  # type: ignore[no-untyped-def]
            calls["httpx_instrumented"] = tracer_provider

    monkeypatch.setattr(observability, "trace", DummyTrace())
    monkeypatch.setattr(observability, "OTLPSpanExporter", DummyExporter)
    monkeypatch.setattr(observability, "BatchSpanProcessor", DummyBatchSpanProcessor)
    monkeypatch.setattr(observability, "TracerProvider", DummyTracerProvider)
    monkeypatch.setattr(observability, "TraceIdRatioBased", DummySampler)
    monkeypatch.setattr(observability, "FastAPIInstrumentor", DummyFastAPIInstrumentor)
    monkeypatch.setattr(observability, "HTTPXClientInstrumentor", DummyHTTPXInstrumentor)

    app = FastAPI()
    updated_settings = test_settings.model_copy(
        update={
            "observability_enabled": True,
            "otel_enabled": True,
            "trace_sample_rate": 0.5,
            "otel_exporter_otlp_endpoint": exporter_endpoint,
        }
    )

    assert configure_tracing(updated_settings, app) is True

    assert "fastapi_instrumented" in calls
    assert "httpx_instrumented" in calls
    assert calls["sample_rate"] == 0.5
    if exporter_endpoint is not None:
        assert calls["exporter"] == exporter_endpoint
    else:
        assert calls.get("exporter") is None
