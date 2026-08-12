"""The account lifecycle, tested for its security properties rather than its
happy path.

Each test here corresponds to a decision that could be quietly undone by a
later refactor: no user enumeration, hashed storage, single use, expiry,
purpose separation, and session revocation on reset.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import hash_token, verify_password
from app.modules.auth.application.account_service import AccountService
from app.modules.auth.domain.exceptions import InvalidVerificationTokenError
from app.modules.auth.infrastructure.models import VerificationPurpose


class _User:
    def __init__(self, email: str = "teacher@example.com") -> None:
        self.uuid = uuid.uuid4()
        self.name = "Teacher"
        self.email = email
        self.password_hash = "unset"
        self.email_verified_at = None


class _Users:
    def __init__(self, user: _User | None) -> None:
        self._user = user

    async def get_by_email(self, email: str) -> _User | None:
        if self._user and self._user.email == email:
            return self._user
        return None

    async def get_by_id(self, user_id: uuid.UUID) -> _User | None:
        if self._user and self._user.uuid == user_id:
            return self._user
        return None


class _Token:
    def __init__(self, **kw) -> None:
        self.__dict__.update(kw)
        self.used_at = None


class _Tokens:
    """In-memory stand-in that keeps the repository's contract."""

    def __init__(self) -> None:
        self.rows: list[_Token] = []

    def add(self, *, user_id, purpose, token_hash, expires_at, requested_ip):
        row = _Token(
            user_id=user_id,
            purpose=purpose,
            token_hash=token_hash,
            expires_at=expires_at,
            requested_ip=requested_ip,
        )
        self.rows.append(row)
        return row

    async def get_usable(self, *, token_hash, purpose):
        now = datetime.now(UTC)
        for row in self.rows:
            if (
                row.token_hash == token_hash
                and row.purpose == purpose
                and row.used_at is None
                and row.expires_at > now
            ):
                return row
        return None

    async def invalidate_outstanding(self, *, user_id, purpose):
        count = 0
        for row in self.rows:
            live = row.used_at is None
            if row.user_id == user_id and row.purpose == purpose and live:
                row.used_at = datetime.now(UTC)
                count += 1
        return count

    @staticmethod
    def mark_used(row) -> None:
        row.used_at = datetime.now(UTC)


class _RefreshTokens:
    def __init__(self) -> None:
        self.revoked_for: list[uuid.UUID] = []

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        self.revoked_for.append(user_id)
        return 2


class _AuthLogs:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def record(
        self, *, event, user_id=None, email=None, ip_address=None, user_agent=None
    ):
        self.events.append(str(event))


class _Session:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class _Mailbox:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def __call__(self, *, to, subject, text, html) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})

    @property
    def last_token(self) -> str:
        """Pull the token out of the link, the way a user's browser would."""
        return self.sent[-1]["text"].split("token=")[1].split()[0]


def _build(user: _User | None):
    tokens, mailbox, refresh, logs, session = (
        _Tokens(),
        _Mailbox(),
        _RefreshTokens(),
        _AuthLogs(),
        _Session(),
    )
    service = AccountService(
        session=session,
        users=_Users(user),
        tokens=tokens,
        refresh_tokens=refresh,
        auth_logs=logs,
        send_email=mailbox,
    )
    return service, tokens, mailbox, refresh, logs


# ------------------------------------------------------------------ reset
async def test_reset_request_for_unknown_address_sends_nothing_and_does_not_raise():
    service, tokens, mailbox, _, logs = _build(None)

    await service.request_password_reset(
        email="nobody@example.com", ip_address="1.2.3.4", user_agent="t"
    )

    # No token, no email, and no exception: the caller cannot tell this address
    # apart from one that exists. The attempt is still recorded.
    assert tokens.rows == []
    assert mailbox.sent == []
    assert "password_reset_requested" in logs.events


async def test_reset_request_stores_only_a_hash():
    user = _User()
    service, tokens, mailbox, _, _ = _build(user)

    await service.request_password_reset(
        email=user.email, ip_address=None, user_agent=None
    )

    raw = mailbox.last_token
    stored = tokens.rows[0].token_hash
    assert stored != raw
    assert stored == hash_token(raw)


async def test_reset_sets_the_password_and_revokes_every_session():
    user = _User()
    service, _, mailbox, refresh, logs = _build(user)
    await service.request_password_reset(
        email=user.email, ip_address=None, user_agent=None
    )

    await service.confirm_password_reset(
        token=mailbox.last_token,
        new_password="BrandNew@123",
        ip_address=None,
        user_agent=None,
    )

    assert verify_password("BrandNew@123", user.password_hash)
    # The whole point: whoever was signed in is signed out.
    assert refresh.revoked_for == [user.uuid]
    assert "password_reset_completed" in logs.events


async def test_a_reset_token_works_exactly_once():
    user = _User()
    service, _, mailbox, _, _ = _build(user)
    await service.request_password_reset(
        email=user.email, ip_address=None, user_agent=None
    )
    token = mailbox.last_token
    await service.confirm_password_reset(
        token=token, new_password="First@12345", ip_address=None, user_agent=None
    )

    with pytest.raises(InvalidVerificationTokenError):
        await service.confirm_password_reset(
            token=token, new_password="Second@12345", ip_address=None, user_agent=None
        )


async def test_requesting_a_new_link_kills_the_previous_one():
    user = _User()
    service, _, mailbox, _, _ = _build(user)
    await service.request_password_reset(
        email=user.email, ip_address=None, user_agent=None
    )
    first = mailbox.last_token
    await service.request_password_reset(
        email=user.email, ip_address=None, user_agent=None
    )
    second = mailbox.last_token

    with pytest.raises(InvalidVerificationTokenError):
        await service.confirm_password_reset(
            token=first, new_password="Nope@123456", ip_address=None, user_agent=None
        )
    await service.confirm_password_reset(
        token=second, new_password="Yes@1234567", ip_address=None, user_agent=None
    )
    assert verify_password("Yes@1234567", user.password_hash)


async def test_an_expired_token_is_refused():
    user = _User()
    service, tokens, mailbox, _, _ = _build(user)
    await service.request_password_reset(
        email=user.email, ip_address=None, user_agent=None
    )
    tokens.rows[0].expires_at = datetime.now(UTC) - timedelta(seconds=1)

    with pytest.raises(InvalidVerificationTokenError):
        await service.confirm_password_reset(
            token=mailbox.last_token,
            new_password="TooLate@123",
            ip_address=None,
            user_agent=None,
        )


async def test_an_unknown_token_is_refused():
    user = _User()
    service, _, _, _, _ = _build(user)

    with pytest.raises(InvalidVerificationTokenError):
        await service.confirm_password_reset(
            token="not-a-real-token-value-at-all",
            new_password="Whatever@123",
            ip_address=None,
            user_agent=None,
        )


# ----------------------------------------------------------- verification
async def test_verification_marks_the_address_and_is_single_use():
    user = _User()
    service, _, mailbox, _, logs = _build(user)
    await service.send_email_verification(user=user)
    token = mailbox.last_token

    verified = await service.confirm_email_verification(
        token=token, ip_address=None, user_agent=None
    )

    assert verified.email_verified_at is not None
    assert "email_verified" in logs.events
    with pytest.raises(InvalidVerificationTokenError):
        await service.confirm_email_verification(
            token=token, ip_address=None, user_agent=None
        )


async def test_verification_is_a_no_op_for_an_already_verified_address():
    user = _User()
    user.email_verified_at = datetime.now(UTC)
    service, tokens, mailbox, _, _ = _build(user)

    await service.send_email_verification(user=user)

    assert tokens.rows == []
    assert mailbox.sent == []


async def test_a_verification_token_cannot_reset_a_password():
    """Purpose is part of the lookup, so tokens are not interchangeable."""
    user = _User()
    service, _, mailbox, _, _ = _build(user)
    await service.send_email_verification(user=user)

    with pytest.raises(InvalidVerificationTokenError):
        await service.confirm_password_reset(
            token=mailbox.last_token,
            new_password="Sneaky@12345",
            ip_address=None,
            user_agent=None,
        )


async def test_purposes_are_stored_separately():
    user = _User()
    service, tokens, _, _, _ = _build(user)

    await service.request_password_reset(
        email=user.email, ip_address=None, user_agent=None
    )
    await service.send_email_verification(user=user)

    purposes = {row.purpose for row in tokens.rows}
    assert purposes == {
        VerificationPurpose.PASSWORD_RESET,
        VerificationPurpose.EMAIL_VERIFICATION,
    }
    # Issuing one must not invalidate the other.
    assert all(row.used_at is None for row in tokens.rows)
