"""Setting a password from inside the session.

The case that made this exist: an account created by signing in with Google
has no password, so the only way in is Google, and nothing in the app said so
or offered to fix it.
"""

import pytest
from sqlalchemy import select

from app.infrastructure.database.session import SessionFactory
from app.modules.auth.application.oauth_service import OAuthService
from app.modules.auth.infrastructure.google_oauth import GoogleIdentity
from app.modules.auth.presentation.schemas import UserResponse
from app.modules.users.infrastructure.models import User

pytestmark = pytest.mark.integration

GOOGLE_EMAIL = "from-google@example.com"


async def _google_account() -> User:
    async with SessionFactory() as session:
        user = await OAuthService(session).sign_in_with_google(
            GoogleIdentity(
                subject="google-sub-9",
                email=GOOGLE_EMAIL,
                email_verified=True,
                name="From Google",
            )
        )
        await session.commit()
        return user


async def _password_hash(email: str) -> str | None:
    async with SessionFactory() as session:
        return await session.scalar(
            select(User.password_hash).where(User.email == email)
        )


async def test_me_says_whether_the_account_has_a_password(auth_client):
    body = (await auth_client.get("/api/v1/auth/me")).json()

    assert body["has_password"] is True
    # The flag is derived from the hash, and the hash itself never leaves.
    assert "password_hash" not in body


async def test_a_google_account_reports_no_password():
    """What the app reads to decide whether to offer setting one."""
    user = await _google_account()

    assert UserResponse.model_validate(user).has_password is False


async def test_the_first_password_needs_no_current_one(auth_client, client):
    """And the session survives: there was nothing to undo."""
    async with SessionFactory() as session:
        user = await session.scalar(select(User).where(User.email == "domain@test.com"))
        user.password_hash = None
        await session.commit()

    response = await auth_client.post(
        "/api/v1/auth/password", json={"password": "Brand@New123"}
    )

    assert response.status_code == 200
    assert response.json()["sessions_ended"] is False
    # Still signed in, so no round trip through the login page.
    assert (await auth_client.get("/api/v1/auth/me")).status_code == 200
    assert await _password_hash("domain@test.com") is not None

    signed_in = await client.post(
        "/api/v1/auth/login",
        json={"email": "domain@test.com", "password": "Brand@New123"},
    )
    assert signed_in.status_code == 200


async def test_changing_a_password_requires_the_current_one(auth_client):
    response = await auth_client.post(
        "/api/v1/auth/password",
        json={"password": "Another@1234", "current_password": "wrong-one"},
    )

    assert response.status_code == 401
    # Unchanged: a wrong current password must not half-apply.
    hash_now = await _password_hash("domain@test.com")
    assert hash_now is not None
    assert (
        await auth_client.post(
            "/api/v1/auth/login",
            json={"email": "domain@test.com", "password": "Senha@123"},
        )
    ).status_code == 200


async def test_changing_a_password_ends_every_session(auth_client):
    response = await auth_client.post(
        "/api/v1/auth/password",
        json={"password": "Another@1234", "current_password": "Senha@123"},
    )

    assert response.status_code == 200
    assert response.json()["sessions_ended"] is True
    # The cookies are cleared, so the app knows to send the person to the
    # sign-in page rather than discovering it on the next request.
    assert (await auth_client.get("/api/v1/auth/me")).status_code == 401


async def test_a_short_password_is_refused(auth_client):
    response = await auth_client.post(
        "/api/v1/auth/password",
        json={"password": "short", "current_password": "Senha@123"},
    )

    assert response.status_code == 422
    assert await _password_hash("domain@test.com") is not None


async def test_a_stranger_cannot_set_anyone_password(client):
    response = await client.post(
        "/api/v1/auth/password", json={"password": "Whatever@123"}
    )

    assert response.status_code == 401
