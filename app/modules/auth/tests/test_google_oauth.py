"""What protects the Google flow, tested apart from Google.

Nothing here talks to Google. The two things that keep a forged callback from
becoming a session are the single-use state and the claim checks on the ID
token, and both can be exercised on their own.
"""

import base64
import json
import time

import pytest

from app.core.config import get_settings
from app.modules.auth.domain.exceptions import InvalidTokenError
from app.modules.auth.infrastructure import google_oauth


def _id_token(**claims) -> str:
    """A token shaped like Google's, with whatever claims the test wants.

    The signature is not checked (see the module docstring of google_oauth),
    so a placeholder segment is enough and no key material is involved.
    """
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def _valid_claims(**overrides) -> dict:
    claims = {
        "aud": get_settings().google_oauth_client_id,
        "iss": "https://accounts.google.com",
        "exp": time.time() + 600,
        "sub": "google-subject-1",
        "email": "Teacher@Example.com",
        "email_verified": True,
        "name": "Teacher",
    }
    claims.update(overrides)
    return claims


class _FakeRedis:
    def __init__(self) -> None:
        self.keys: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.keys[key] = value

    async def delete(self, key: str) -> int:
        return 1 if self.keys.pop(key, None) is not None else 0


async def test_state_is_stored_and_the_url_carries_it():
    redis = _FakeRedis()
    url = await google_oauth.start(redis)

    assert url.startswith(google_oauth.AUTHORIZE_URL)
    assert "response_type=code" in url
    # The state in the URL is the one the server remembers, not a copy the
    # browser could have chosen.
    (state,) = [k.removeprefix("oauth:state:") for k in redis.keys]
    assert f"state={state}" in url


async def test_a_state_works_once():
    redis = _FakeRedis()
    await google_oauth.start(redis)
    (key,) = list(redis.keys)
    state = key.removeprefix("oauth:state:")

    await google_oauth.consume_state(redis, state)

    # A replayed callback finds nothing to consume.
    with pytest.raises(InvalidTokenError):
        await google_oauth.consume_state(redis, state)


@pytest.mark.parametrize("state", [None, "", "never-issued"])
async def test_a_state_this_server_did_not_issue_is_refused(state):
    with pytest.raises(InvalidTokenError):
        await google_oauth.consume_state(_FakeRedis(), state)


async def test_claims_are_read_from_a_well_formed_token(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "google_oauth_client_id", "this-app", raising=False
    )
    identity = google_oauth._read_id_token(_id_token(**_valid_claims(aud="this-app")))

    assert identity.subject == "google-subject-1"
    # Addresses are compared against stored ones, so they are normalised here
    # rather than at every call site.
    assert identity.email == "teacher@example.com"
    assert identity.email_verified is True
    assert identity.name == "Teacher"


async def test_a_token_meant_for_another_application_is_refused(monkeypatch):
    """The check that makes a genuine token from elsewhere worthless here."""
    monkeypatch.setattr(
        get_settings(), "google_oauth_client_id", "this-app", raising=False
    )
    with pytest.raises(InvalidTokenError):
        google_oauth._read_id_token(_id_token(**_valid_claims(aud="someone-else")))


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://accounts.evil.example"},
        {"exp": time.time() - 1},
        {"sub": None},
        {"email": None},
    ],
    ids=["wrong issuer", "expired", "no subject", "no email"],
)
async def test_tokens_missing_what_matters_are_refused(monkeypatch, claims):
    monkeypatch.setattr(
        get_settings(), "google_oauth_client_id", "this-app", raising=False
    )
    with pytest.raises(InvalidTokenError):
        google_oauth._read_id_token(
            _id_token(**_valid_claims(aud="this-app", **claims))
        )


async def test_a_token_that_is_not_a_token_is_refused():
    for garbage in ("", "not-a-jwt", "a.b"):
        with pytest.raises(InvalidTokenError):
            google_oauth._read_id_token(garbage)


async def test_the_name_falls_back_to_the_address(monkeypatch):
    """Google does not always send a name; an account still needs one."""
    monkeypatch.setattr(
        get_settings(), "google_oauth_client_id", "this-app", raising=False
    )
    identity = google_oauth._read_id_token(
        _id_token(
            **_valid_claims(aud="this-app", email="Teacher@Example.com", name=None)
        )
    )
    # The address is lowered because it is compared; the name is only shown,
    # so it keeps the case the person actually wrote.
    assert identity.name == "Teacher"
