"""Integration test: security headers are present on every response."""

import pytest

pytestmark = pytest.mark.integration


class TestSecurityHeaders:
    async def test_headers_are_set_on_api_responses(self, client):
        resp = await client.get("/health")

        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Referrer-Policy"] == "no-referrer"
        assert "Content-Security-Policy" in resp.headers
        assert "Permissions-Policy" in resp.headers

    async def test_api_csp_is_locked_down(self, client):
        resp = await client.get("/health")
        assert "default-src 'none'" in resp.headers["Content-Security-Policy"]

    async def test_headers_present_even_on_401(self, client):
        # An unauthenticated request still gets the hardening headers.
        resp = await client.get("/api/v1/plans")
        assert resp.status_code == 401
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
