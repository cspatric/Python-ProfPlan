"""Integration tests for the auth flow against real Postgres + Redis."""

import pytest
from sqlalchemy import text

from app.infrastructure.database.session import SessionFactory

pytestmark = pytest.mark.integration

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


async def test_login_sets_cookies_and_me_returns_user(client, user_factory):
    await user_factory(email="a@test.com")

    resp = await client.post(
        LOGIN, json={"email": "a@test.com", "password": "Senha@123"}
    )

    assert resp.status_code == 200
    assert "access_token" in client.cookies
    assert "refresh_token" in client.cookies

    me = await client.get(ME)
    assert me.status_code == 200
    assert me.json()["email"] == "a@test.com"


async def test_me_without_login_is_unauthorized(client):
    resp = await client.get(ME)
    assert resp.status_code == 401


async def test_login_with_wrong_password_is_unauthorized(client, user_factory):
    await user_factory(email="b@test.com")

    resp = await client.post(LOGIN, json={"email": "b@test.com", "password": "wrong"})
    assert resp.status_code == 401


async def test_refresh_rotates_and_old_token_is_rejected(client, user_factory):
    await user_factory(email="c@test.com")
    await client.post(LOGIN, json={"email": "c@test.com", "password": "Senha@123"})
    old_refresh = client.cookies.get("refresh_token")

    rotated = await client.post(REFRESH)
    assert rotated.status_code == 200
    assert client.cookies.get("refresh_token") != old_refresh

    # Present the old (now revoked) refresh token -> reuse detected.
    client.cookies.clear()
    reused = await client.post(
        REFRESH, headers={"Cookie": f"refresh_token={old_refresh}"}
    )
    assert reused.status_code == 401


async def test_login_is_rate_limited_after_max_attempts(client, user_factory):
    await user_factory(email="d@test.com")

    codes = []
    for _ in range(6):
        resp = await client.post(
            LOGIN, json={"email": "d@test.com", "password": "wrong"}
        )
        codes.append(resp.status_code)

    assert codes[:5] == [401, 401, 401, 401, 401]
    assert codes[5] == 429


async def test_logout_revokes_session(client, user_factory):
    await user_factory(email="e@test.com")
    await client.post(LOGIN, json={"email": "e@test.com", "password": "Senha@123"})

    out = await client.post(LOGOUT)
    assert out.status_code == 200

    # Session revoked and cookies cleared -> refreshing must fail.
    again = await client.post(REFRESH)
    assert again.status_code == 401


async def test_login_writes_audit_log(client, user_factory):
    await user_factory(email="f@test.com")
    await client.post(LOGIN, json={"email": "f@test.com", "password": "Senha@123"})

    async with SessionFactory() as session:
        count = await session.scalar(
            text("SELECT count(*) FROM auth_logs WHERE event = 'LOGIN_SUCCESS'")
        )
    assert count == 1
