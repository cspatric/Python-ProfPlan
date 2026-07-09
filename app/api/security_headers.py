"""Security response headers.

Adds the standard hardening headers to every response so the API (and any HTML
it serves) is protected against clickjacking, MIME sniffing, referrer leakage
and, over HTTPS, protocol downgrade. The interactive docs (`/docs`, `/redoc`)
need a looser Content-Security-Policy because Swagger UI / ReDoc load assets
from a CDN and run inline scripts; every other path gets a locked-down policy.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# The API returns JSON that browsers never execute, so it can deny everything.
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

# Swagger UI / ReDoc need their CDN assets and inline bootstrap script.
_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'"
)

_DOCS_PATHS = ("/docs", "/redoc")
_HSTS_VALUE = "max-age=63072000; includeSubDomains; preload"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security headers to every response."""

    def __init__(self, app, *, hsts: bool = False) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        is_docs = request.url.path.startswith(_DOCS_PATHS)
        response.headers["Content-Security-Policy"] = _DOCS_CSP if is_docs else _API_CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )
        # Disable the legacy, buggy XSS auditor (modern best practice).
        response.headers["X-XSS-Protection"] = "0"
        if self._hsts:
            response.headers["Strict-Transport-Security"] = _HSTS_VALUE
        return response
