"""Integration tests for the academic items CRUD flow (JSON + soft delete)."""

from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration

BASE = "/api/v1/academic-items"


def _payload(module_id: str) -> dict:
    return {
        "module_id": module_id,
        "title": "Exam 1",
        "content": {"questions": 3},
        "metadata": {
            "starts_at": "2026-09-10T14:00:00Z",
            "ends_at": "2026-09-10T16:00:00Z",
            "is_graded": True,
            "weight": 30,
            "is_individual": True,
            "estimated_duration": 120,
        },
    }


async def test_create_stores_content_and_metadata(auth_client, module_id):
    created = await auth_client.post(BASE, json=_payload(module_id))
    assert created.status_code == 201
    body = created.json()
    assert body["content"] == {"questions": 3}
    assert body["metadata"]["is_graded"] is True
    assert body["metadata"]["weight"] == 30
    assert body["metadata"]["estimated_duration"] == 120


async def test_update_metadata_and_soft_delete(auth_client, module_id):
    created = await auth_client.post(BASE, json=_payload(module_id))
    aid = created.json()["uuid"]

    updated = await auth_client.patch(
        f"{BASE}/{aid}",
        json={"metadata": {"is_graded": True, "weight": 40}},
    )
    assert updated.status_code == 200
    assert updated.json()["metadata"]["weight"] == 40

    listed = await auth_client.get(f"{BASE}?module_id={module_id}")
    assert any(i["uuid"] == aid for i in listed.json())

    # Soft delete: the row is hidden from reads afterwards.
    assert (await auth_client.delete(f"{BASE}/{aid}")).status_code == 204
    assert (await auth_client.get(f"{BASE}/{aid}")).status_code == 404
    listed_after = await auth_client.get(f"{BASE}?module_id={module_id}")
    assert all(i["uuid"] != aid for i in listed_after.json())


async def test_create_with_unowned_module_is_rejected(auth_client):
    resp = await auth_client.post(BASE, json=_payload(str(uuid4())))
    assert resp.status_code == 422
