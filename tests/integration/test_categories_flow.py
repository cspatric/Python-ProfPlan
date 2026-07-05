"""Integration tests for academic item categories and their types."""

from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration

CATEGORIES = "/api/v1/academic-item-categories"
TYPES = "/api/v1/academic-item-category-types"


async def test_category_full_crud_as_admin(admin_client):
    created = await admin_client.post(CATEGORIES, json={"name": "Evaluations"})
    assert created.status_code == 201
    cid = created.json()["uuid"]

    assert (await admin_client.get(CATEGORIES)).status_code == 200
    assert (await admin_client.get(f"{CATEGORIES}/{cid}")).status_code == 200

    updated = await admin_client.patch(f"{CATEGORIES}/{cid}", json={"name": "Tests"})
    assert updated.json()["name"] == "Tests"

    assert (await admin_client.delete(f"{CATEGORIES}/{cid}")).status_code == 204


async def test_type_crud_and_parent_validation_as_admin(admin_client, category_id):
    created = await admin_client.post(
        TYPES, json={"academic_item_category_id": category_id, "name": "Exam"}
    )
    assert created.status_code == 201
    tid = created.json()["uuid"]

    listed = await admin_client.get(f"{TYPES}?category_id={category_id}")
    assert listed.status_code == 200
    assert any(t["uuid"] == tid for t in listed.json())

    updated = await admin_client.patch(f"{TYPES}/{tid}", json={"name": "Written exam"})
    assert updated.json()["name"] == "Written exam"

    assert (await admin_client.delete(f"{TYPES}/{tid}")).status_code == 204


async def test_type_with_missing_parent_is_rejected(admin_client):
    resp = await admin_client.post(
        TYPES,
        json={"academic_item_category_id": str(uuid4()), "name": "Orphan"},
    )
    assert resp.status_code == 422


async def test_non_admin_cannot_write_catalog(auth_client):
    # Regular users can read the catalog but not modify it.
    assert (await auth_client.get(CATEGORIES)).status_code == 200
    forbidden = await auth_client.post(CATEGORIES, json={"name": "Nope"})
    assert forbidden.status_code == 403
