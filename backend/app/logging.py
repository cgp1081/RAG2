"""Structured logging configuration for the FastAPI service."""

from __future__ import annotations

import logging
import sys
import time
import uuid
from contextvars import ContextVar

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp
from structlog.stdlib import add_log_level, add_logger_name

_REQUEST_ID_CONTEXT: ContextVar[str | None] = ContextVar("request_id", default=None)
_LOGGING_CONFIGURED = False


def configure_logging(level: str = "INFO") -> None:
    """Initialise structlog once with JSON output."""

    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)

    processors = [
        structlog.contextvars.merge_contextvars,
        add_log_level,
        add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        cache_logger_on_first_use=True,
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )

    _LOGGING_CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return the configured structlog logger."""

    return structlog.get_logger(name)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Attach `X-Request-ID` header and emit structured request logs."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._logger = get_logger("backend.request")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = _REQUEST_ID_CONTEXT.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id
        start_time = time.monotonic()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            self._logger.exception(
                "request",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=duration_ms,
            )
            raise
        else:
            response.headers["X-Request-ID"] = request_id
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            log_kwargs = {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            }
            if response.status_code >= 500:
                self._logger.error("request", **log_kwargs)
            else:
                self._logger.info("request", **log_kwargs)
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
            _REQUEST_ID_CONTEXT.reset(token)


__all__ = ["configure_logging", "get_logger", "RequestLoggingMiddleware"]
