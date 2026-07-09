"""Per-IP request rate limiting (slowapi + Redis).

A global default limit is applied to every route via ``SlowAPIMiddleware`` to
absorb request floods/DoS. Sensitive routes opt into stricter limits with the
``auth_limit`` / ``expensive_limit`` decorators. Counters live in Redis so the
limit holds across multiple API replicas (not just per-process memory).

Requests are keyed by the real client IP: behind Traefik the peer address is the
proxy, so the first hop of ``X-Forwarded-For`` is used when present.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import get_settings

_settings = get_settings()


def client_ip(request: Request) -> str:
    """Real client IP: first ``X-Forwarded-For`` hop (Traefik), else the peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(
    key_func=client_ip,
    default_limits=[_settings.rate_limit_default],
    storage_uri=_settings.rate_limit_storage_url,
    enabled=_settings.rate_limit_enabled,
    headers_enabled=True,
    strategy="fixed-window",
)

# Stricter, reusable limits for sensitive routes. Decorated endpoints must take a
# ``request: Request`` (and, for POSTs, ``response: Response``) parameter so
# slowapi can read the client key and attach the rate-limit headers.
auth_limit = limiter.limit(_settings.rate_limit_auth)
expensive_limit = limiter.limit(_settings.rate_limit_expensive)
