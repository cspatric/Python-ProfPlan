"""Unit tests for per-IP rate limiting (slowapi wiring).

Builds a throwaway app with its own in-memory limiter so the test is independent
of the global RATE_LIMIT_ENABLED setting and never touches Redis.
"""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.rate_limit import client_ip


class _FakeRequest:
    def __init__(self, headers, client_host="10.0.0.9"):
        self.headers = headers
        self.client = type("C", (), {"host": client_host})()


class TestClientIp:
    def test_prefers_first_x_forwarded_for_hop(self):
        req = _FakeRequest({"x-forwarded-for": "203.0.113.7, 10.0.0.1"})
        assert client_ip(req) == "203.0.113.7"

    def test_falls_back_to_peer_when_no_forwarded_header(self):
        req = _FakeRequest({}, client_host="198.51.100.2")
        assert client_ip(req) == "198.51.100.2"


def _build_app(limit: str) -> FastAPI:
    # Fixed key so every request shares one bucket, regardless of test client IP.
    # NB: slowapi only passes the request if the key func's parameter is named
    # "request" (see slowapi.extension.__evaluate_limits) — matching client_ip.
    limiter = Limiter(
        key_func=lambda request: "test-client",
        default_limits=[limit],
        storage_uri="memory://",
        enabled=True,
        headers_enabled=True,
    )
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/ping")
    def ping(request: Request) -> dict[str, str]:
        return {"pong": "ok"}

    return app


class TestRateLimitMiddleware:
    def test_requests_over_the_limit_get_429(self):
        client = TestClient(_build_app("3/minute"))

        statuses = [client.get("/ping").status_code for _ in range(5)]

        assert statuses[:3] == [200, 200, 200]
        assert statuses[3] == 429
        assert statuses[4] == 429

    def test_limit_headers_are_exposed(self):
        client = TestClient(_build_app("2/minute"))
        resp = client.get("/ping")
        # slowapi advertises the remaining budget so clients can back off.
        assert "x-ratelimit-limit" in {k.lower() for k in resp.headers}
