"""Centralized exception handlers registered on the FastAPI app.

Every endpoint benefits from these — domain code just raises an AppError
subclass and gets a consistent JSON error with the right status code. Unexpected
errors are logged and returned as a generic 500 (never leaked, never a 200).

Server errors (5xx) are also recorded on the active OpenTelemetry span, so the
exception and its stacktrace show up on the request's trace. When tracing is
disabled the span is a no-op, so this is always safe to call.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.shared.exceptions.base import AppError

logger = logging.getLogger("app.errors")


def _record_on_span(exc: Exception, message: str) -> None:
    """Attach the exception + stacktrace to the current trace span as an error."""
    span = trace.get_current_span()
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, message))


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Map an expected AppError to its HTTP status and detail."""
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        _record_on_span(exc, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log the unexpected error, record it on the span, return 500."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    _record_on_span(exc, "Internal server error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the application exception handlers to the app."""
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
