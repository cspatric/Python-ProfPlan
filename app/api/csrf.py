"""CSRF protection (double-submit cookie).

The access/refresh cookies are HttpOnly (a script can't read them), so a
same-site attacker page can still make the browser *send* them — that's what
this guards against. A non-HttpOnly ``csrf_token`` cookie is set alongside
the auth cookies (see ``auth/presentation/router.py``); the frontend must
mirror its value into the ``X-CSRF-Token`` header on every unsafe request.
A cross-site page can trigger the request but can't read the cookie to
produce a matching header.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

_settings = get_settings()

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# No session/csrf cookie exists yet before these succeed.
_EXEMPT_PATHS = frozenset(
    {f"{_settings.api_prefix}/auth/login", f"{_settings.api_prefix}/auth/register"}
)
CSRF_COOKIE_NAME = "csrf_token"
_CSRF_HEADER_NAME = "x-csrf-token"


class CSRFMiddleware(BaseHTTPMiddleware):
    """Reject unsafe requests whose CSRF header doesn't match the cookie."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        has_session_cookie = bool(
            request.cookies.get(_settings.access_cookie_name)
            or request.cookies.get(_settings.refresh_cookie_name)
        )
        if (
            not _settings.csrf_protection_enabled
            or request.method in _SAFE_METHODS
            or request.url.path in _EXEMPT_PATHS
            # No ambient session cookie to ride along with -> no CSRF risk;
            # let the request fall through to the normal 401 auth check.
            or not has_session_cookie
        ):
            return await call_next(request)

        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(_CSRF_HEADER_NAME)
        if not cookie_token or not header_token or cookie_token != header_token:
            return JSONResponse(
                {"detail": "Missing or invalid CSRF token"}, status_code=403
            )
        return await call_next(request)
