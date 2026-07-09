"""Integration tests for plan creation + generation wiring.

The full AI generation (planner + fan-out) needs an LLM and is exercised locally;
CI runs with PLAN_GENERATION_ENABLED=false, so these cover the CI-safe paths:
the plain-plan branch and the document-selection validation that runs before any
AI call.
"""

from uuid import uuid4

import pytest

from app.core.config import get_settings

pytestmark = pytest.mark.integration

_PLAN = {
    "starts_at": "2026-08-01",
    "ends_at": "2026-12-15",
    "class_duration": 50,
    "class_per_week": 2,
}


class TestCreatePlan:
    async def test_creates_a_plain_plan_when_generation_is_disabled(
        self, auth_client, subject_id
    ):
        if get_settings().plan_generation_enabled:
            pytest.skip("generation enabled: covered by the local LLM run")

        resp = await auth_client.post(
            "/api/v1/plans", json={"subject_id": subject_id, **_PLAN}
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["generation"] is None  # no AI call was made
        assert body["uuid"]

        # The plain plan is persisted and retrievable.
        got = await auth_client.get(f"/api/v1/plans/{body['uuid']}")
        assert got.status_code == 200

    async def test_rejects_unowned_documents_before_any_ai_call(
        self, auth_client, subject_id
    ):
        # Document validation happens first, so this holds regardless of the flag.
        resp = await auth_client.post(
            "/api/v1/plans",
            json={
                "subject_id": subject_id,
                "document_ids": [str(uuid4())],  # not owned by anyone
                **_PLAN,
            },
        )
        assert resp.status_code == 404
