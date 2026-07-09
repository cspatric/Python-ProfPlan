"""Integration tests for the auth flow against real Postgres + Redis."""

import pytest
from sqlalchemy import text

from app.api.csrf import CSRF_COOKIE_NAME
from app.infrastructure.database.session import SessionFactory

pytestmark = pytest.mark.integration

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


async def test_register_creates_account_and_signs_in(client):
    resp = await client.post(
        REGISTER,
        json={"name": "New User", "email": "new@test.com", "password": "Senha@123"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new@test.com"
    assert body["name"] == "New User"
    assert "access_token" in client.cookies
    assert "refresh_token" in client.cookies

    me = await client.get(ME)
    assert me.status_code == 200
    assert me.json()["email"] == "new@test.com"


async def test_register_duplicate_email_conflicts(client):
    payload = {"name": "Dup", "email": "dup@test.com", "password": "Senha@123"}
    first = await client.post(REGISTER, json=payload)
    assert first.status_code == 201

    second = await client.post(REGISTER, json=payload)
    assert second.status_code == 409


async def test_register_then_login_works(client):
    await client.post(
        REGISTER,
        json={"name": "Flow", "email": "flow@test.com", "password": "Senha@123"},
    )
    client.cookies.clear()

    resp = await client.post(
        LOGIN, json={"email": "flow@test.com", "password": "Senha@123"}
    )
    assert resp.status_code == 200


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

    # Present the old (now revoked) refresh token, keeping a currently-valid
    # CSRF pair so the request clears CSRF and exercises reuse detection.
    csrf_token = client.cookies.get(CSRF_COOKIE_NAME)
    client.cookies.clear()
    reused = await client.post(
        REFRESH,
        headers={
            "Cookie": f"refresh_token={old_refresh}; {CSRF_COOKIE_NAME}={csrf_token}",
            "X-CSRF-Token": csrf_token,
        },
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


async def test_login_account_lockout_persists_across_ips(client, user_factory):
    """A distributed attacker (many IPs) against one account still locks out."""
    await user_factory(email="g@test.com")

    codes = []
    for i in range(6):
        resp = await client.post(
            LOGIN,
            json={"email": "g@test.com", "password": "wrong"},
            headers={"X-Forwarded-For": f"10.0.0.{i}"},
        )
        codes.append(resp.status_code)

    assert codes[:5] == [401, 401, 401, 401, 401]
    assert codes[5] == 429


async def test_mutating_request_without_csrf_header_is_forbidden(client, user_factory):
    await user_factory(email="h@test.com")
    await client.post(LOGIN, json={"email": "h@test.com", "password": "Senha@123"})

    resp = await client.post(
        "/api/v1/subjects",
        json={"name": "Mathematics"},
        headers={"X-CSRF-Token": ""},  # override the fixture's auto-synced header
    )
    assert resp.status_code == 403
