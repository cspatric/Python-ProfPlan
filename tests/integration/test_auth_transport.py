"""Integration tests for the two accepted access-token transports.

The first-party web app uses the HttpOnly cookie; a mobile app or third-party
integration sends the same signed JWT as a bearer header. This pins that the
header path works with no cookie present at all — and that CSRF, which exists
for ambient cookies, does not stand in its way.
"""

import pytest

from app.core.config import get_settings

pytestmark = pytest.mark.integration

BASE = "/api/v1/subjects"
_COOKIE = get_settings().access_cookie_name


def _as_api_client(client) -> str:
    """Strip everything a browser would send, and return the access token."""
    token = client.cookies.get(_COOKIE)
    assert token, "login should have set the access-token cookie"
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    return token


async def test_bearer_header_reads_without_any_cookie(auth_client):
    token = _as_api_client(auth_client)

    resp = await auth_client.get(BASE, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200


async def test_bearer_header_writes_without_a_csrf_token(auth_client):
    """No browser attaches a bearer header, so no CSRF check applies to it."""
    token = _as_api_client(auth_client)

    resp = await auth_client.post(
        BASE,
        json={"name": "From a mobile app"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201
    # The owner still comes from the token, never from the body.
    assert resp.json()["user_id"]


async def test_garbage_bearer_token_is_rejected(auth_client):
    _as_api_client(auth_client)

    resp = await auth_client.get(BASE, headers={"Authorization": "Bearer not-a-jwt"})

    assert resp.status_code == 401


async def test_still_no_credential_is_still_401(auth_client):
    _as_api_client(auth_client)

    assert (await auth_client.get(BASE)).status_code == 401
