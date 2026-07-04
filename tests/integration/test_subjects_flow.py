"""Integration tests for the subjects CRUD flow."""

import pytest

pytestmark = pytest.mark.integration

BASE = "/api/v1/subjects"


async def test_requires_authentication(client):
    resp = await client.get(BASE)
    assert resp.status_code == 401


async def test_full_crud(auth_client):
    created = await auth_client.post(
        BASE, json={"name": "Physics", "knowledge_area": "STEM"}
    )
    assert created.status_code == 201
    subject = created.json()
    sid = subject["uuid"]
    assert subject["name"] == "Physics"

    listed = await auth_client.get(BASE)
    assert listed.status_code == 200
    assert any(s["uuid"] == sid for s in listed.json())

    fetched = await auth_client.get(f"{BASE}/{sid}")
    assert fetched.status_code == 200

    updated = await auth_client.patch(f"{BASE}/{sid}", json={"name": "Physics II"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Physics II"

    deleted = await auth_client.delete(f"{BASE}/{sid}")
    assert deleted.status_code == 204

    missing = await auth_client.get(f"{BASE}/{sid}")
    assert missing.status_code == 404


async def test_user_cannot_see_other_users_subject(auth_client, user_factory):
    created = await auth_client.post(BASE, json={"name": "Private"})
    sid = created.json()["uuid"]

    # A second user logs in on a separate client instance.
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    await user_factory(email="intruder@test.com")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as other:
        await other.post(
            "/api/v1/auth/login",
            json={"email": "intruder@test.com", "password": "Senha@123"},
        )
        resp = await other.get(f"{BASE}/{sid}")
        assert resp.status_code == 404
