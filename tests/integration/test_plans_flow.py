"""Integration tests for the plans CRUD flow."""

import pytest

pytestmark = pytest.mark.integration

BASE = "/api/v1/plans"


def _payload(subject_id: str) -> dict:
    return {
        "subject_id": subject_id,
        "starts_at": "2026-08-01",
        "ends_at": "2026-12-15",
        "class_duration": 50,
        "class_per_week": 2,
        "total_weight": 100,
    }


async def test_full_crud(auth_client, subject_id):
    created = await auth_client.post(BASE, json=_payload(subject_id))
    assert created.status_code == 201
    pid = created.json()["uuid"]

    assert (await auth_client.get(BASE)).status_code == 200
    assert (await auth_client.get(f"{BASE}/{pid}")).status_code == 200

    updated = await auth_client.patch(f"{BASE}/{pid}", json={"class_per_week": 3})
    assert updated.status_code == 200
    assert updated.json()["class_per_week"] == 3

    assert (await auth_client.delete(f"{BASE}/{pid}")).status_code == 204


async def test_create_with_unowned_subject_is_rejected(auth_client):
    from uuid import uuid4

    resp = await auth_client.post(BASE, json=_payload(str(uuid4())))
    assert resp.status_code == 422


async def test_create_with_inverted_dates_is_rejected(auth_client, subject_id):
    payload = _payload(subject_id)
    payload["starts_at"], payload["ends_at"] = payload["ends_at"], payload["starts_at"]
    resp = await auth_client.post(BASE, json=payload)
    assert resp.status_code == 422
