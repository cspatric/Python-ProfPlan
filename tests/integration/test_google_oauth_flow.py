"""Signing in with Google, against the real tables.

The interesting cases are not "it works": they are what happens when an
address already belongs to somebody. That is where a provider sign-in either
stays an authentication or quietly becomes a way into another account, so it is
tested here with real rows rather than a stand-in for the session.
"""

import importlib
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.redis.client import redis_client
from app.modules.auth.application.oauth_service import OAuthService
from app.modules.auth.domain.exceptions import EmailNotVerifiedError
from app.modules.auth.infrastructure import google_oauth
from app.modules.auth.infrastructure.google_oauth import GoogleIdentity
from app.modules.auth.infrastructure.models import Provider, UserProvider
from app.modules.users.infrastructure.models import User

pytestmark = pytest.mark.integration


def _identity(**overrides) -> GoogleIdentity:
    values = {
        "subject": "google-sub-1",
        "email": "teacher@example.com",
        "email_verified": True,
        "name": "Teacher",
    }
    values.update(overrides)
    return GoogleIdentity(**values)


async def _sign_in(identity: GoogleIdentity) -> User:
    async with SessionFactory() as session:
        user = await OAuthService(session).sign_in_with_google(identity)
        await session.commit()
        return user


async def test_a_first_sign_in_creates_a_passwordless_account():
    user = await _sign_in(_identity())

    assert user.email == "teacher@example.com"
    # No password at all, rather than a random hash nothing can ever match:
    # this is what makes "does this account have a password" answerable.
    assert user.password_hash is None
    # Google proved the mailbox, so the address is already verified.
    assert user.email_verified_at is not None

    async with SessionFactory() as session:
        link = await session.scalar(
            select(UserProvider).where(UserProvider.user_id == user.uuid)
        )
        assert link is not None
        assert link.provider_user_id == "google-sub-1"


async def test_signing_in_again_reuses_the_same_account():
    first = await _sign_in(_identity())
    second = await _sign_in(_identity())

    assert first.uuid == second.uuid
    async with SessionFactory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(UserProvider))
        ) == 1
        # The provider row is created once, on first use, not per sign-in.
        assert await session.scalar(select(func.count()).select_from(Provider)) == 1


async def test_the_subject_identifies_the_account_not_the_address():
    """Somebody changing their Google address keeps their account."""
    first = await _sign_in(_identity())
    again = await _sign_in(_identity(email="new-address@example.com"))

    assert again.uuid == first.uuid


async def test_a_verified_address_links_to_the_existing_account(user_factory):
    existing = await user_factory(email="teacher@example.com")

    user = await _sign_in(_identity())

    assert user.uuid == existing.uuid
    # The password still works: linking a provider adds a way in, it does not
    # replace the one that was there.
    assert user.password_hash is not None
    async with SessionFactory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1


async def test_an_unverified_address_cannot_claim_an_existing_account(user_factory):
    """The account takeover case, refused.

    Without this, anyone able to get a provider to assert an address, an
    unverified one is asserted on nothing more than typing it, would be handed
    the account that owns it here.
    """
    await user_factory(email="teacher@example.com")

    with pytest.raises(EmailNotVerifiedError):
        await _sign_in(_identity(email_verified=False))

    async with SessionFactory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(UserProvider))
        ) == 0


async def test_an_unverified_address_nobody_owns_still_creates_an_account():
    """The refusal is about the collision, not about the flag."""
    user = await _sign_in(_identity(email_verified=False))

    assert user.uuid is not None
    # Nothing proved the mailbox this time, so it stays unverified.
    assert user.email_verified_at is None


async def test_a_passwordless_account_cannot_be_signed_into_with_a_password(client):
    """The other half of nullable password_hash.

    An account created by Google has nothing to verify a password against, and
    the login endpoint has to treat that as a failure rather than as a match.
    """
    await _sign_in(_identity())

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "teacher@example.com", "password": "Senha@123"},
    )

    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# The endpoints themselves.
#
# They are only registered when a client id and secret are configured, which
# they are not in the test environment, so the fixture below sets them and
# rebuilds the router before mounting it on a small app of its own. Nothing
# here reaches Google: the exchange is replaced, which is exactly the part that
# would need the internet and a real secret.
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def _client_for_a_rebuilt_router():
    """Mount the auth router as it is under the environment set by the caller.

    The routes are registered at import time, so the module has to be reloaded
    after the environment changes. The reload is undone afterwards, or the rest
    of the suite would inherit whichever configuration ran last.
    """
    from app.api.rate_limit import limiter
    from app.modules.auth.presentation import router as router_module

    importlib.reload(router_module)

    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router_module.router, prefix="/api/v1")

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=False
        ) as http_client:
            yield http_client
    finally:
        get_settings.cache_clear()
        importlib.reload(router_module)


@pytest_asyncio.fixture
async def google_client(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "this-app")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "not-a-real-secret")
    get_settings.cache_clear()
    async with _client_for_a_rebuilt_router() as http_client:
        yield http_client


@pytest_asyncio.fixture
async def plain_client(monkeypatch):
    """The same app with the feature off, whatever the developer's .env says.

    Asserting the absence of a route against the shared app made this test
    depend on a file that is not in the repository: it passed until somebody
    configured Google locally, and then failed for a reason that had nothing
    to do with the change in front of them.
    """
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    get_settings.cache_clear()
    async with _client_for_a_rebuilt_router() as http_client:
        yield http_client


async def test_the_endpoints_do_not_exist_without_a_client_id(plain_client):
    """A button that cannot work is worse than one that is honestly absent."""
    assert (await plain_client.get("/api/v1/auth/oauth/google")).status_code == 404
    # And the sign-in page is told, so it does not draw the button either.
    listing = await plain_client.get("/api/v1/auth/providers")
    assert listing.json() == {"google": False}


async def test_the_provider_listing_follows_the_configuration(google_client):
    listing = await google_client.get("/api/v1/auth/providers")
    assert listing.json() == {"google": True}


async def test_starting_the_flow_redirects_to_google(google_client):
    response = await google_client.get("/api/v1/auth/oauth/google")

    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/")
    assert "client_id=this-app" in location
    # The state went to Redis, so the callback has something to consume.
    assert len(await redis_client.keys("oauth:state:*")) == 1


async def test_the_callback_signs_the_person_in(google_client, monkeypatch):
    start = await google_client.get("/api/v1/auth/oauth/google")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    async def _exchange(code: str) -> GoogleIdentity:
        assert code == "the-one-time-code"
        return _identity()

    monkeypatch.setattr(google_oauth, "exchange", _exchange)
    response = await google_client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "the-one-time-code", "state": state},
    )

    assert response.status_code == 307
    assert response.headers["location"] == get_settings().oauth_success_redirect
    # The session is in the cookies, the same ones a password login sets.
    settings = get_settings()
    assert response.cookies.get(settings.access_cookie_name)
    assert response.cookies.get(settings.refresh_cookie_name)
    assert response.cookies.get("csrf_token")

    async with SessionFactory() as session:
        user = await session.scalar(select(User).where(User.email == _identity().email))
        assert user is not None
        assert user.last_login_at is not None


async def test_a_forged_callback_gets_no_session(google_client, monkeypatch):
    """No state was issued for this, so there is nothing to consume."""
    monkeypatch.setattr(
        google_oauth, "exchange", lambda code: pytest.fail("should not be reached")
    )

    response = await google_client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "stolen", "state": "never-issued"},
    )

    assert response.status_code == 307
    assert "oauth=failed" in response.headers["location"]
    assert not response.cookies
    async with SessionFactory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 0


async def test_pressing_cancel_at_google_is_not_an_error(google_client):
    response = await google_client.get(
        "/api/v1/auth/oauth/google/callback", params={"error": "access_denied"}
    )

    assert response.status_code == 307
    assert response.headers["location"].startswith(
        get_settings().oauth_failure_redirect
    )


async def test_a_refused_link_ends_on_the_login_page(
    google_client, monkeypatch, user_factory
):
    """The takeover refusal, seen from the browser rather than the service."""
    await user_factory(email="teacher@example.com")
    start = await google_client.get("/api/v1/auth/oauth/google")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    async def _exchange(code: str) -> GoogleIdentity:
        return _identity(email_verified=False)

    monkeypatch.setattr(google_oauth, "exchange", _exchange)
    response = await google_client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "code", "state": state},
    )

    assert "oauth=failed" in response.headers["location"]
    assert not response.cookies
