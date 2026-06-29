"""Unit tests for AuthService using in-memory fakes (no DB/Redis)."""

import uuid
from datetime import UTC, datetime

import pytest

from app.core.security import hash_password
from app.modules.auth.application.service import AuthService
from app.modules.auth.domain.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    RateLimitedError,
    TokenReuseError,
)
from app.modules.auth.infrastructure.models import AuthEvent, RefreshToken
from app.modules.users.domain.entities import UserStatus
from app.modules.users.infrastructure.models import User

PASSWORD = "Senha@123"


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class FakeUserRepository:
    def __init__(self, users: list[User] | None = None) -> None:
        self._by_email = {u.email: u for u in users or []}
        self._by_id = {u.uuid: u for u in users or []}
        self.logged_in: list[uuid.UUID] = []

    async def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email.lower())

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._by_id.get(user_id)

    async def mark_logged_in(self, user: User) -> None:
        user.last_login_at = datetime.now(UTC)
        self.logged_in.append(user.uuid)


class FakeRefreshTokenRepository:
    def __init__(self) -> None:
        self.sessions: dict[uuid.UUID, RefreshToken] = {}

    async def create(self, **kwargs) -> RefreshToken:
        row = RefreshToken(
            uuid=kwargs["session_id"],
            user_id=kwargs["user_id"],
            token_hash=kwargs["token_hash"],
            expires_at=kwargs["expires_at"],
            user_agent=kwargs["user_agent"],
            ip_address=kwargs["ip_address"],
        )
        self.sessions[row.uuid] = row
        return row

    async def get_by_id(self, session_id: uuid.UUID) -> RefreshToken | None:
        return self.sessions.get(session_id)

    async def revoke(self, row: RefreshToken) -> None:
        row.revoked_at = datetime.now(UTC)

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        count = 0
        for row in self.sessions.values():
            if row.user_id == user_id and row.revoked_at is None:
                row.revoked_at = datetime.now(UTC)
                count += 1
        return count


class FakeAuthLogRepository:
    def __init__(self) -> None:
        self.events: list[AuthEvent] = []

    async def record(self, **kwargs) -> None:
        self.events.append(kwargs["event"])


class FakeRateLimiter:
    def __init__(self, *, blocked: bool = False) -> None:
        self.blocked = blocked
        self.failures = 0
        self.resets = 0

    async def is_blocked(self, identifier: str) -> bool:
        return self.blocked

    async def register_failure(self, identifier: str) -> None:
        self.failures += 1

    async def reset(self, identifier: str) -> None:
        self.resets += 1


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_user(status: UserStatus = UserStatus.ACTIVE) -> User:
    return User(
        uuid=uuid.uuid4(),
        name="Test User",
        email="test@profplan.com",
        password_hash=hash_password(PASSWORD),
        status=status,
    )


def make_service(
    *,
    users: FakeUserRepository,
    refresh: FakeRefreshTokenRepository | None = None,
    logs: FakeAuthLogRepository | None = None,
    limiter: FakeRateLimiter | None = None,
    session: FakeSession | None = None,
) -> AuthService:
    return AuthService(
        session=session or FakeSession(),
        users=users,
        refresh_tokens=refresh or FakeRefreshTokenRepository(),
        auth_logs=logs or FakeAuthLogRepository(),
        rate_limiter=limiter or FakeRateLimiter(),
    )


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
async def test_login_success_issues_tokens_and_logs() -> None:
    user = make_user()
    refresh = FakeRefreshTokenRepository()
    logs = FakeAuthLogRepository()
    limiter = FakeRateLimiter()
    service = make_service(
        users=FakeUserRepository([user]),
        refresh=refresh,
        logs=logs,
        limiter=limiter,
    )

    tokens = await service.login(
        email="test@profplan.com",
        password=PASSWORD,
        ip_address="1.1.1.1",
        user_agent="ua",
    )

    assert tokens.access_token and tokens.refresh_token
    assert len(refresh.sessions) == 1
    assert AuthEvent.LOGIN_SUCCESS in logs.events
    assert limiter.resets == 1


async def test_login_wrong_password_fails_and_counts_attempt() -> None:
    logs = FakeAuthLogRepository()
    limiter = FakeRateLimiter()
    service = make_service(
        users=FakeUserRepository([make_user()]), logs=logs, limiter=limiter
    )

    with pytest.raises(InvalidCredentialsError):
        await service.login(
            email="test@profplan.com",
            password="wrong",
            ip_address="1.1.1.1",
            user_agent="ua",
        )

    assert AuthEvent.LOGIN_FAILED in logs.events
    assert limiter.failures == 1


async def test_login_unknown_email_fails() -> None:
    logs = FakeAuthLogRepository()
    service = make_service(users=FakeUserRepository([]), logs=logs)

    with pytest.raises(InvalidCredentialsError):
        await service.login(
            email="nobody@profplan.com",
            password=PASSWORD,
            ip_address=None,
            user_agent=None,
        )
    assert AuthEvent.LOGIN_FAILED in logs.events


async def test_login_inactive_user_fails() -> None:
    user = make_user(status=UserStatus.SUSPENDED)
    service = make_service(users=FakeUserRepository([user]))

    with pytest.raises(InvalidCredentialsError):
        await service.login(
            email=user.email,
            password=PASSWORD,
            ip_address=None,
            user_agent=None,
        )


async def test_login_blocked_by_rate_limiter() -> None:
    logs = FakeAuthLogRepository()
    service = make_service(
        users=FakeUserRepository([make_user()]),
        logs=logs,
        limiter=FakeRateLimiter(blocked=True),
    )

    with pytest.raises(RateLimitedError):
        await service.login(
            email="test@profplan.com",
            password=PASSWORD,
            ip_address="1.1.1.1",
            user_agent="ua",
        )
    assert AuthEvent.LOGIN_RATE_LIMITED in logs.events


# --------------------------------------------------------------------------- #
# Refresh
# --------------------------------------------------------------------------- #
async def test_refresh_rotates_and_revokes_old_session() -> None:
    user = make_user()
    refresh = FakeRefreshTokenRepository()
    logs = FakeAuthLogRepository()
    service = make_service(
        users=FakeUserRepository([user]), refresh=refresh, logs=logs
    )

    first = await service.login(
        email=user.email, password=PASSWORD, ip_address=None, user_agent=None
    )
    first_session_id = next(iter(refresh.sessions))

    second = await service.refresh(
        raw_token=first.refresh_token, ip_address=None, user_agent=None
    )

    assert second.refresh_token != first.refresh_token
    assert refresh.sessions[first_session_id].revoked_at is not None
    assert len(refresh.sessions) == 2
    assert AuthEvent.TOKEN_REFRESHED in logs.events


async def test_refresh_reuse_revokes_all_sessions() -> None:
    user = make_user()
    refresh = FakeRefreshTokenRepository()
    logs = FakeAuthLogRepository()
    service = make_service(
        users=FakeUserRepository([user]), refresh=refresh, logs=logs
    )

    first = await service.login(
        email=user.email, password=PASSWORD, ip_address=None, user_agent=None
    )
    await service.refresh(
        raw_token=first.refresh_token, ip_address=None, user_agent=None
    )

    with pytest.raises(TokenReuseError):
        await service.refresh(
            raw_token=first.refresh_token, ip_address=None, user_agent=None
        )

    assert AuthEvent.TOKEN_REUSE_DETECTED in logs.events
    assert all(s.revoked_at is not None for s in refresh.sessions.values())


async def test_refresh_with_missing_or_garbage_token_fails() -> None:
    service = make_service(users=FakeUserRepository([make_user()]))

    with pytest.raises(InvalidTokenError):
        await service.refresh(raw_token=None, ip_address=None, user_agent=None)
    with pytest.raises(InvalidTokenError):
        await service.refresh(
            raw_token="not.a.jwt", ip_address=None, user_agent=None
        )


# --------------------------------------------------------------------------- #
# Logout
# --------------------------------------------------------------------------- #
async def test_logout_revokes_current_session() -> None:
    user = make_user()
    refresh = FakeRefreshTokenRepository()
    logs = FakeAuthLogRepository()
    service = make_service(
        users=FakeUserRepository([user]), refresh=refresh, logs=logs
    )

    tokens = await service.login(
        email=user.email, password=PASSWORD, ip_address=None, user_agent=None
    )
    session_id = next(iter(refresh.sessions))

    await service.logout(
        raw_token=tokens.refresh_token, ip_address=None, user_agent=None
    )

    assert refresh.sessions[session_id].revoked_at is not None
    assert AuthEvent.LOGOUT in logs.events


async def test_logout_all_revokes_every_session() -> None:
    user = make_user()
    refresh = FakeRefreshTokenRepository()
    logs = FakeAuthLogRepository()
    service = make_service(
        users=FakeUserRepository([user]), refresh=refresh, logs=logs
    )

    await service.login(
        email=user.email, password=PASSWORD, ip_address=None, user_agent=None
    )
    revoked = await service.logout_all(
        user_id=user.uuid, ip_address=None, user_agent=None
    )

    assert revoked == 1
    assert AuthEvent.LOGOUT_ALL in logs.events
