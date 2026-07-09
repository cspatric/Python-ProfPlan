"""Load test for ProfPlan — AI-free endpoints only.

Measures the capacity of the HTTP + Postgres + Redis path (auth session, CRUD,
listing, provider health) WITHOUT calling any LLM, so it is free to run as often
as you like. The AI generation/ask paths are deliberately excluded: their ceiling
is the LLM provider (Gemini quota / Ollama CPU), not this architecture — see
perf/README.md.

To isolate infrastructure capacity from the per-IP rate limiter, every request is
sent with a distinct ``X-Forwarded-For`` so the limiter never becomes the
bottleneck. (The limiter itself is covered by app/api/tests/test_rate_limit.py.)
"""

import itertools
import uuid

from locust import HttpUser, between, task

_ip_counter = itertools.count(1)


def _next_ip() -> str:
    """A unique client IP per request → its own rate-limit bucket."""
    n = next(_ip_counter)
    return f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


class ProfPlanUser(HttpUser):
    """A simulated teacher browsing subjects/plans (read-heavy, some writes)."""

    wait_time = between(0.05, 0.2)

    def _headers(self) -> dict[str, str]:
        return {"X-Forwarded-For": _next_ip()}

    def on_start(self) -> None:
        # One account per simulated user; register also sets the auth cookie.
        # NB: use a real TLD — email-validator rejects reserved ones like .local.
        email = f"load-{uuid.uuid4().hex[:12]}@load.example.com"
        self._password = "Senha@123"
        resp = self.client.post(
            "/api/v1/auth/register",
            json={"name": "Load", "email": email, "password": self._password},
            headers=self._headers(),
            name="POST /auth/register",
        )
        if resp.status_code not in (200, 201):
            self.client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": self._password},
                headers=self._headers(),
                name="POST /auth/login",
            )
        # Seed one subject so the read endpoints return data.
        resp = self.client.post(
            "/api/v1/subjects",
            json={"name": "Load subject"},
            headers=self._headers(),
            name="POST /subjects",
        )
        self.subject_id = resp.json().get("uuid") if resp.status_code == 201 else None

    @task(6)
    def list_subjects(self) -> None:
        self.client.get(
            "/api/v1/subjects", headers=self._headers(), name="GET /subjects"
        )

    @task(4)
    def list_plans(self) -> None:
        self.client.get("/api/v1/plans", headers=self._headers(), name="GET /plans")

    @task(3)
    def me(self) -> None:
        self.client.get("/api/v1/auth/me", headers=self._headers(), name="GET /auth/me")

    @task(2)
    def ai_health(self) -> None:
        self.client.get(
            "/api/v1/ai/health", headers=self._headers(), name="GET /ai/health"
        )

    @task(2)
    def liveness(self) -> None:
        self.client.get("/health", headers=self._headers(), name="GET /health")

    @task(1)
    def create_subject(self) -> None:
        self.client.post(
            "/api/v1/subjects",
            json={"name": f"S-{uuid.uuid4().hex[:6]}"},
            headers=self._headers(),
            name="POST /subjects",
        )
