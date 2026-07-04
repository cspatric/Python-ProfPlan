"""Integration tests for the plan modules CRUD flow."""

from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration

BASE = "/api/v1/modules"


def _payload(plan_id: str) -> dict:
    return {
        "plan_id": plan_id,
        "title": "Introduction",
        "start_at": "2026-08-01",
        "ends_at": "2026-09-01",
    }


async def test_full_crud_and_list_by_plan(auth_client, plan_id):
    created = await auth_client.post(BASE, json=_payload(plan_id))
    assert created.status_code == 201
    mid = created.json()["uuid"]

    listed = await auth_client.get(f"{BASE}?plan_id={plan_id}")
    assert listed.status_code == 200
    assert any(m["uuid"] == mid for m in listed.json())

    updated = await auth_client.patch(f"{BASE}/{mid}", json={"title": "Intro II"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "Intro II"

    assert (await auth_client.delete(f"{BASE}/{mid}")).status_code == 204
    assert (await auth_client.get(f"{BASE}/{mid}")).status_code == 404


async def test_create_with_unowned_plan_is_rejected(auth_client):
    resp = await auth_client.post(BASE, json=_payload(str(uuid4())))
    assert resp.status_code == 422
