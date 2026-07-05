"""HTTP request-logging middleware.

Emits one structured (JSON) log line per request capturing as much context as we
can safely gather — who did it (the authenticated user), what they called, from
where, the outcome and how long it took. Each line carries the trace_id, so a
log entry links straight to its OpenTelemetry span in Grafana (Loki -> Tempo).
"""

import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.access")

# Liveness/metrics endpoints are polled constantly; logging them is pure noise.
_SKIP_PATHS = frozenset({"/health", "/ready", "/metrics"})


def _client_ip(request: Request) -> str | None:
    """Real client IP, honouring the X-Forwarded-For added by Traefik."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with rich context and the acting user."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        request_id = request.headers.get("x-request-id") or uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()

        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            fields: dict[str, object | None] = {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query or None,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client_ip": _client_ip(request),
                "user_agent": request.headers.get("user-agent"),
                "referer": request.headers.get("referer"),
                "host": request.headers.get("host"),
                "scheme": request.url.scheme,
                "http_version": request.scope.get("http_version"),
                "request_bytes": request.headers.get("content-length"),
                # Populated by the auth dependency once the user is resolved.
                "user_id": getattr(request.state, "user_id", None),
                "user_email": getattr(request.state, "user_email", None),
                "user_role": getattr(request.state, "user_role", None),
            }
            span_context = trace.get_current_span().get_span_context()
            if span_context.is_valid:
                fields["trace_id"] = format(span_context.trace_id, "032x")
                fields["span_id"] = format(span_context.span_id, "016x")

            logger.info("http_request", extra=fields)
