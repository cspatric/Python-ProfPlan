"""Password reset and email verification over real HTTP, Postgres and Redis.

The unit tests cover the service's rules. These cover the parts only a real
stack can prove: that the token actually round-trips through the database, that
the reset really ends the session, and that the endpoints answer the way the
API contract says they do.

Email delivery is monkeypatched at the queue boundary. Asserting that Celery
received the right message is the useful part; SMTP itself is Mailpit's job in
development and the provider's in production.
"""

import re

import pytest

from app.modules.auth.presentation import dependencies as auth_dependencies

pytestmark = pytest.mark.integration

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
ME = "/api/v1/auth/me"
RESET = "/api/v1/auth/password-reset"
RESET_CONFIRM = "/api/v1/auth/password-reset/confirm"
VERIFY = "/api/v1/auth/email-verification"
VERIFY_CONFIRM = "/api/v1/auth/email-verification/confirm"


class _Outbox:
    """Captures what would have been queued for the worker."""

    def __init__(self) -> None:
        self.messages: list[dict] = []

    def __call__(self, *, to: str, subject: str, text: str, html: str | None) -> None:
        self.messages.append({"to": to, "subject": subject, "text": text})

    def token_for(self, to: str, subject_contains: str) -> str:
        for message in reversed(self.messages):
            if message["to"] == to and subject_contains in message["subject"]:
                return re.search(r"token=([\w\-.]+)", message["text"]).group(1)
        raise AssertionError(f"no {subject_contains!r} email for {to}")


@pytest.fixture
def outbox(monkeypatch) -> _Outbox:
    """Swap the Celery hand-off for an in-memory list."""
    box = _Outbox()
    monkeypatch.setattr(auth_dependencies, "queue_via_celery", box)
    return box


async def _register(client, outbox, email: str = "reset@test.com"):
    resp = await client.post(
        REGISTER, json={"name": "Reset User", "email": email, "password": "Senha@123"}
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------- reset
async def test_reset_request_is_accepted_for_an_unknown_address(client, outbox):
    resp = await client.post(RESET, json={"email": "ghost@test.com"})

    # 202 and nothing sent: the response must not reveal that the account is
    # missing, and no mail may go to an address we have no relationship with.
    assert resp.status_code == 202
    assert outbox.messages == []


async def test_reset_request_and_unknown_address_are_indistinguishable(client, outbox):
    await _register(client, outbox, email="real@test.com")
    outbox.messages.clear()

    known = await client.post(RESET, json={"email": "real@test.com"})
    unknown = await client.post(RESET, json={"email": "ghost@test.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    # One email, for the address that exists.
    assert [m["to"] for m in outbox.messages] == ["real@test.com"]


async def test_reset_changes_the_password_and_ends_every_session(client, outbox):
    await _register(client, outbox, email="reset@test.com")
    assert (await client.get(ME)).status_code == 200

    await client.post(RESET, json={"email": "reset@test.com"})
    token = outbox.token_for("reset@test.com", "Reset")
    confirm = await client.post(
        RESET_CONFIRM, json={"token": token, "password": "NovaSenha@456"}
    )
    assert confirm.status_code == 200

    # The refresh token issued before the reset is dead, so the session cannot
    # be renewed. The access token still works until it expires (15 minutes),
    # which is the documented trade-off of stateless access tokens.
    assert (await client.post(REFRESH)).status_code in (401, 403)

    old = await client.post(
        LOGIN, json={"email": "reset@test.com", "password": "Senha@123"}
    )
    assert old.status_code == 401
    new = await client.post(
        LOGIN, json={"email": "reset@test.com", "password": "NovaSenha@456"}
    )
    assert new.status_code == 200


async def test_a_reset_token_cannot_be_replayed(client, outbox):
    await _register(client, outbox, email="replay@test.com")
    await client.post(RESET, json={"email": "replay@test.com"})
    token = outbox.token_for("replay@test.com", "Reset")

    first = await client.post(
        RESET_CONFIRM, json={"token": token, "password": "Primeira@123"}
    )
    second = await client.post(
        RESET_CONFIRM, json={"token": token, "password": "Segunda@1234"}
    )

    assert first.status_code == 200
    assert second.status_code == 401


async def test_a_garbage_token_is_rejected(client):
    resp = await client.post(
        RESET_CONFIRM,
        json={"token": "0" * 40, "password": "Qualquer@123"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------- verification
async def test_registration_queues_a_verification_email(client, outbox):
    body = await _register(client, outbox, email="verify@test.com")

    assert body["email_verified_at"] is None
    assert [m["to"] for m in outbox.messages] == ["verify@test.com"]
    assert "Confirm" in outbox.messages[0]["subject"]


async def test_confirming_verification_marks_the_account(client, outbox):
    await _register(client, outbox, email="verify@test.com")
    token = outbox.token_for("verify@test.com", "Confirm")

    resp = await client.post(VERIFY_CONFIRM, json={"token": token})

    assert resp.status_code == 200
    assert resp.json()["email_verified_at"] is not None
    # Single use, like the reset token.
    assert (await client.post(VERIFY_CONFIRM, json={"token": token})).status_code == 401


async def test_resending_verification_requires_a_session(client):
    resp = await client.post(VERIFY)
    assert resp.status_code == 401


async def test_resending_verification_invalidates_the_previous_link(client, outbox):
    await _register(client, outbox, email="resend@test.com")
    first = outbox.token_for("resend@test.com", "Confirm")

    resend = await client.post(VERIFY)
    assert resend.status_code == 202
    second = outbox.token_for("resend@test.com", "Confirm")
    assert second != first

    assert (await client.post(VERIFY_CONFIRM, json={"token": first})).status_code == 401
    ok = await client.post(VERIFY_CONFIRM, json={"token": second})
    assert ok.status_code == 200
