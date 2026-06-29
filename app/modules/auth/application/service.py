"""Authentication use cases (login, refresh rotation, logout)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_token,
    verify_password,
)
from app.modules.auth.domain.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    RateLimitedError,
    TokenReuseError,
)
from app.modules.auth.infrastructure.models import AuthEvent
from app.modules.auth.infrastructure.rate_limit import LoginRateLimiter
from app.modules.auth.infrastructure.repository import (
    AuthLogRepository,
    RefreshTokenRepository,
)
from app.modules.users.domain.entities import UserStatus
from app.modules.users.infrastructure.models import User
from app.modules.users.infrastructure.repository import UserRepository


@dataclass(slots=True)
class IssuedTokens:
    """Result of issuing a new pair of tokens."""

    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    user: User


class AuthService:
    """Coordinates the authentication flow across repositories and security."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        auth_logs: AuthLogRepository,
        rate_limiter: LoginRateLimiter,
    ) -> None:
        self._session = session
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._auth_logs = auth_logs
        self._rate_limiter = rate_limiter

    async def login(
        self,
        *,
        email: str,
        password: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> IssuedTokens:
        """Authenticate a user with email and password."""
        rl_key = ip_address or "unknown"
        if await self._rate_limiter.is_blocked(rl_key):
            await self._auth_logs.record(
                event=AuthEvent.LOGIN_RATE_LIMITED,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            await self._session.commit()
            raise RateLimitedError

        user = await self._users.get_by_email(email)
        if (
            user is None
            or user.status != UserStatus.ACTIVE
            or not verify_password(password, user.password_hash)
        ):
            await self._rate_limiter.register_failure(rl_key)
            await self._auth_logs.record(
                event=AuthEvent.LOGIN_FAILED,
                user_id=user.uuid if user else None,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            await self._session.commit()
            raise InvalidCredentialsError

        await self._rate_limiter.reset(rl_key)
        await self._users.mark_logged_in(user)
        tokens = await self._issue_tokens(user, ip_address, user_agent)
        await self._auth_logs.record(
            event=AuthEvent.LOGIN_SUCCESS,
            user_id=user.uuid,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._session.commit()
        return tokens

    async def refresh(
        self,
        *,
        raw_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> IssuedTokens:
        """Validate and rotate a refresh token."""
        payload = self._decode_refresh(raw_token)
        session_id = uuid.UUID(payload["sid"])
        user_id = uuid.UUID(payload["sub"])

        session = await self._refresh_tokens.get_by_id(session_id)
        if session is None or session.user_id != user_id:
            raise InvalidTokenError

        # A signature-valid token whose session is already revoked means the
        # token was reused (possible theft): revoke every session as defense.
        if session.revoked_at is not None:
            await self._refresh_tokens.revoke_all_for_user(user_id)
            await self._auth_logs.record(
                event=AuthEvent.TOKEN_REUSE_DETECTED,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            await self._session.commit()
            raise TokenReuseError

        if session.token_hash != hash_token(raw_token or ""):
            raise InvalidTokenError
        if session.expires_at <= datetime.now(UTC):
            raise InvalidTokenError

        user = await self._users.get_by_id(user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise InvalidTokenError

        # Rotation: invalidate the presented session and issue a fresh one.
        await self._refresh_tokens.revoke(session)
        tokens = await self._issue_tokens(user, ip_address, user_agent)
        await self._auth_logs.record(
            event=AuthEvent.TOKEN_REFRESHED,
            user_id=user_id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._session.commit()
        return tokens

    async def logout(
        self,
        *,
        raw_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        """Revoke the session bound to the given refresh token."""
        try:
            payload = self._decode_refresh(raw_token)
        except InvalidTokenError:
            return

        session = await self._refresh_tokens.get_by_id(uuid.UUID(payload["sid"]))
        if session is not None and session.revoked_at is None:
            await self._refresh_tokens.revoke(session)
            await self._auth_logs.record(
                event=AuthEvent.LOGOUT,
                user_id=session.user_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            await self._session.commit()

    async def logout_all(
        self,
        *,
        user_id: uuid.UUID,
        ip_address: str | None,
        user_agent: str | None,
    ) -> int:
        """Revoke every active session of the user."""
        revoked = await self._refresh_tokens.revoke_all_for_user(user_id)
        await self._auth_logs.record(
            event=AuthEvent.LOGOUT_ALL,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._session.commit()
        return revoked

    async def _issue_tokens(
        self, user: User, ip_address: str | None, user_agent: str | None
    ) -> IssuedTokens:
        session_id = uuid.uuid4()
        subject = str(user.uuid)
        access_token, access_exp = create_access_token(subject)
        refresh_token, refresh_exp = create_refresh_token(
            subject, str(session_id)
        )
        await self._refresh_tokens.create(
            session_id=session_id,
            user_id=user.uuid,
            token_hash=hash_token(refresh_token),
            expires_at=refresh_exp,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return IssuedTokens(
            access_token=access_token,
            access_expires_at=access_exp,
            refresh_token=refresh_token,
            refresh_expires_at=refresh_exp,
            user=user,
        )

    @staticmethod
    def _decode_refresh(raw_token: str | None) -> dict:
        if not raw_token:
            raise InvalidTokenError
        from app.core.security import decode_refresh_token

        try:
            return decode_refresh_token(raw_token)
        except (jwt.PyJWTError, KeyError, ValueError) as exc:
            raise InvalidTokenError from exc
