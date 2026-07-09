"""Integration tests for the AI provider endpoints (health + toggle wiring).

These do not call an LLM: /ai/health reads provider state (DB + circuit) and the
toggle error paths are validated before any provider row is touched.
"""

import pytest

pytestmark = pytest.mark.integration

_PROVIDERS = {"claude", "openai", "gemini", "ollama"}


class TestAiHealth:
    async def test_lists_the_fallback_chain_with_status(self, auth_client):
        resp = await auth_client.get("/api/v1/ai/health")

        assert resp.status_code == 200
        providers = resp.json()["providers"]
        assert {p["name"] for p in providers} == _PROVIDERS
        # Ordered by fallback position, each with a runtime status shape.
        assert [p["order"] for p in providers] == sorted(p["order"] for p in providers)
        ollama = next(p for p in providers if p["name"] == "ollama")
        assert ollama["configured"] is True  # local, needs no API key

    async def test_requires_authentication(self, client):
        resp = await client.get("/api/v1/ai/health")
        assert resp.status_code == 401


class TestProviderToggle:
    async def test_ollama_cannot_be_disabled(self, admin_client):
        resp = await admin_client.patch(
            "/api/v1/ai/providers/ollama", json={"enabled": False}
        )
        assert resp.status_code == 409

    async def test_unknown_provider_returns_404(self, admin_client):
        resp = await admin_client.patch(
            "/api/v1/ai/providers/does-not-exist", json={"enabled": False}
        )
        assert resp.status_code == 404

    async def test_non_admin_cannot_toggle(self, auth_client):
        resp = await auth_client.patch(
            "/api/v1/ai/providers/gemini", json={"enabled": False}
        )
        assert resp.status_code == 403
