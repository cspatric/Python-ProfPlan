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


async def test_creating_a_plan_returns_before_the_planner_runs(
    auth_client, subject_id, monkeypatch
):
    """The request must not wait on the AI.

    The planner costs up to a minute, and a browser that lost the connection
    meanwhile left the teacher with nothing on screen and a plan in the
    database. Creation now answers with a run to watch, and the drafting is
    queued.
    """
    from app.core.config import get_settings
    from app.infrastructure.celery.tasks import generate as generate_tasks

    queued: list[tuple] = []
    monkeypatch.setattr(
        generate_tasks.generate_plan, "delay", lambda *args: queued.append(args)
    )
    monkeypatch.setattr(get_settings(), "plan_generation_enabled", True, raising=False)

    resp = await auth_client.post(
        "/api/v1/plans",
        json={
            "subject_id": subject_id,
            "starts_at": "2026-09-01",
            "ends_at": "2026-10-01",
            "class_duration": 50,
            "class_per_week": 2,
            "exam_count": 2,
            "item_kinds": ["conteudo", "prova"],
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    # A run to poll, already open, with nothing generated yet.
    assert body["generation"]["status"] == "planning"
    assert body["generation"]["items"] == []
    # And the drafting was handed to a worker rather than done here.
    assert len(queued) == 1
    assert queued[0][0] == body["uuid"]
