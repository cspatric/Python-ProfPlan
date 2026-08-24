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


async def test_response_carries_the_generation_status(auth_client, module_id):
    """The status is what the page reads to tell "being written" from "empty".

    It has a default on the schema, so forgetting to pass it produces a valid
    response that claims every item was made by hand. That is exactly what
    happened, and the activity page showed "no material of its own" on items
    the workers had not reached yet.
    """
    created = await auth_client.post(
        BASE,
        json={"module_id": module_id, "title": "Queued item"},
    )
    assert created.status_code == 201
    item_id = created.json()["uuid"]

    # A hand-made item has no generation status, and the field must be present
    # in the payload rather than missing from it.
    assert "generation_status" in created.json()

    fetched = await auth_client.get(f"{BASE}/{item_id}")
    assert "generation_status" in fetched.json()

    listed = await auth_client.get(f"{BASE}?module_id={module_id}")
    assert all("generation_status" in item for item in listed.json())


class TestItemFigures:
    """The figure endpoints.

    The bytes are streamed by the API rather than served from object storage,
    because MinIO has no published port and Traefik cannot route to it — there
    is no URL for a browser to open. So the ownership check on these is the same
    one every other read uses.
    """

    async def test_an_item_with_no_figures_answers_with_an_empty_list(
        self, auth_client, subject_id, plan_id, module_id
    ):
        created = await auth_client.post(
            BASE, json={"module_id": module_id, "title": "Neurons"}
        )
        item_id = created.json()["uuid"]

        resp = await auth_client.get(f"{BASE}/{item_id}/figures")

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_figures_require_authentication(self, client, auth_client, module_id):
        created = await auth_client.post(
            BASE, json={"module_id": module_id, "title": "Neurons"}
        )
        item_id = created.json()["uuid"]
        auth_client.cookies.clear()

        assert (await client.get(f"{BASE}/{item_id}/figures")).status_code == 401

    async def test_another_teachers_item_is_not_readable(
        self, auth_client, module_id, user_factory, client
    ):
        created = await auth_client.post(
            BASE, json={"module_id": module_id, "title": "Neurons"}
        )
        item_id = created.json()["uuid"]

        await user_factory(email="someone-else@test.com")
        await client.post(
            "/api/v1/auth/login",
            json={"email": "someone-else@test.com", "password": "Str0ng@Pass1"},
        )

        assert (await client.get(f"{BASE}/{item_id}/figures")).status_code == 404

    async def test_a_figure_that_does_not_exist_is_404(self, auth_client, module_id):
        created = await auth_client.post(
            BASE, json={"module_id": module_id, "title": "Neurons"}
        )
        item_id = created.json()["uuid"]

        resp = await auth_client.get(
            f"{BASE}/{item_id}/figures/00000000-0000-0000-0000-000000000000"
        )

        assert resp.status_code == 404
