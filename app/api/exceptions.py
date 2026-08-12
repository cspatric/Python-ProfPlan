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
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

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


async def _pool_timeout_handler(
    request: Request, exc: PoolTimeoutError
) -> JSONResponse:
    """DB pool exhaustion is backpressure, not a bug: 503 + Retry-After.

    Under overload every connection is busy and the acquire wait times out.
    Returning 500 here made saturation indistinguishable from real defects in
    the dashboards, and clients/load balancers won't retry a 500 — a 503 with
    Retry-After is both honest and retryable. (Load-tested: this is the first
    failure the stack shows past its capacity ceiling — see perf/RESULTS.md.)
    """
    logger.warning(
        "DB pool exhausted on %s %s — shedding load with 503",
        request.method,
        request.url.path,
    )
    _record_on_span(exc, "Database connection pool exhausted")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Server is at capacity, retry shortly"},
        headers={"Retry-After": "1"},
    )


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
    app.add_exception_handler(PoolTimeoutError, _pool_timeout_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
