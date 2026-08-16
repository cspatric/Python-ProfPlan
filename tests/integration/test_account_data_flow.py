"""Leaving, and taking your material with you.

Both are rights rather than features, and both have a failure mode that a
happy-path test would not see: an export that is missing the part only this
product has, and a deletion that leaves the data where it was under a flag.
"""

import json

import pytest
from sqlalchemy import func, select

from app.infrastructure.database.session import SessionFactory
from app.modules.auth.infrastructure.models import AuthLog
from app.modules.subjects.infrastructure.models import Subject
from app.modules.users.application.account_data_service import ERASED_EMAIL
from app.modules.users.infrastructure.models import User

pytestmark = pytest.mark.integration


async def test_the_export_carries_the_material_and_not_just_the_account(
    auth_client, subject_id, plan_id
):
    response = await auth_client.get("/api/v1/users/me/export")

    assert response.status_code == 200
    # A file, because this is a person exercising a right rather than a client
    # calling an API.
    assert "attachment" in response.headers["content-disposition"]

    data = json.loads(response.text)
    assert data["account"]["email"] == "domain@test.com"
    assert [s["uuid"] for s in data["subjects"]] == [subject_id]
    assert [p["uuid"] for p in data["plans"]] == [plan_id]
    # Self-describing: whoever receives this file has to know what it is.
    assert data["format"] == "profplan/account-export/1"


async def test_the_export_never_carries_the_password(auth_client):
    data = json.loads((await auth_client.get("/api/v1/users/me/export")).text)

    assert "password" not in json.dumps(data).lower().replace("has_password", "")
    assert data["account"]["has_password"] is True


async def test_a_stranger_cannot_export_an_account(client):
    assert (await client.get("/api/v1/users/me/export")).status_code == 401


async def test_deleting_needs_the_password(auth_client):
    response = await auth_client.post(
        "/api/v1/users/me/delete", json={"password": "not-the-password"}
    )

    assert response.status_code == 401
    async with SessionFactory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1


async def test_deleting_removes_the_account_and_what_it_owns(auth_client, subject_id):
    response = await auth_client.post(
        "/api/v1/users/me/delete", json={"password": "Senha@123"}
    )

    assert response.status_code == 200
    async with SessionFactory() as session:
        # Gone, not flagged: a deleted_at on a row still holding somebody's
        # teaching material and address has erased nothing.
        assert await session.scalar(select(func.count()).select_from(User)) == 0
        assert await session.scalar(select(func.count()).select_from(Subject)) == 0


async def test_the_security_log_keeps_the_event_without_the_person(auth_client):
    """An audit trail that the account it incriminates can empty is not an
    audit trail; one that keeps names forever is not erasure."""
    async with SessionFactory() as session:
        before = await session.scalar(select(func.count()).select_from(AuthLog))
    assert before > 0

    await auth_client.post("/api/v1/users/me/delete", json={"password": "Senha@123"})

    async with SessionFactory() as session:
        rows = (await session.scalars(select(AuthLog))).all()
    assert len(rows) == before
    assert all(row.email in (ERASED_EMAIL, None) for row in rows)
    assert all(row.user_id is None for row in rows)


async def test_an_account_with_no_password_confirms_with_its_address(
    client, user_factory
):
    """A Google account has no password to prove. Typing the address is what
    makes the deletion deliberate."""
    user = await user_factory(email="passwordless@test.com")
    async with SessionFactory() as session:
        row = await session.get(User, user.uuid)
        row.password_hash = None
        await session.commit()

    from app.modules.auth.application.oauth_service import OAuthService
    from app.modules.auth.infrastructure.google_oauth import GoogleIdentity

    async with SessionFactory() as session:
        signed_in = await OAuthService(session).sign_in_with_google(
            GoogleIdentity(
                subject="sub-erase",
                email="passwordless@test.com",
                email_verified=True,
                name="No Password",
            )
        )
        await session.commit()
        assert signed_in.uuid == user.uuid

    # Signed in the only way that account can be: a token issued for it,
    # which is what the Google callback puts in the cookie.
    from app.core.security import create_access_token

    token, _ = create_access_token(str(user.uuid))
    client.cookies.set("access_token", token)
    # The double-submit pair, which a real sign-in would have set together.
    client.cookies.set("csrf_token", "a-token")
    client.headers["X-CSRF-Token"] = "a-token"

    wrong = await client.post(
        "/api/v1/users/me/delete", json={"confirm_email": "someone@else.com"}
    )
    assert wrong.status_code == 401

    right = await client.post(
        "/api/v1/users/me/delete", json={"confirm_email": "PASSWORDLESS@test.com"}
    )
    assert right.status_code == 200
