"""Account lifecycle: password reset and email verification.

Four decisions in here are security decisions rather than implementation
details, and each one has a comment saying why, because they all look like
they could be simplified until you know what they are for:

* the reset request answers the same way whether or not the account exists;
* the token is stored hashed, and only the hash is ever compared;
* confirming a reset revokes every session, not just the current one;
* asking for a new link kills the previous one.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password, hash_token
from app.modules.auth.domain.emails import (
    RenderedEmail,
    email_verification_email,
    password_reset_email,
)
from app.modules.auth.domain.exceptions import InvalidVerificationTokenError
from app.modules.auth.infrastructure.models import AuthEvent, VerificationPurpose
from app.modules.auth.infrastructure.repository import (
    AuthLogRepository,
    RefreshTokenRepository,
    VerificationTokenRepository,
)
from app.modules.users.infrastructure.models import User
from app.modules.users.infrastructure.repository import UserRepository

logger = logging.getLogger("app.auth")

# 32 bytes from the OS CSPRNG, url-safe. Long enough that guessing is not a
# threat model, short enough to survive a mail client's line wrapping.
_TOKEN_BYTES = 32


class AccountService:
    """Password reset and email verification use cases."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        users: UserRepository,
        tokens: VerificationTokenRepository,
        refresh_tokens: RefreshTokenRepository,
        auth_logs: AuthLogRepository,
        send_email,
    ) -> None:
        self._session = session
        self._users = users
        self._tokens = tokens
        self._refresh_tokens = refresh_tokens
        self._auth_logs = auth_logs
        # Injected rather than imported so tests do not need a broker, and so
        # the request never depends on the mail server being reachable.
        self._send_email = send_email

    # ------------------------------------------------------------ password
    async def request_password_reset(
        self, *, email: str, ip_address: str | None, user_agent: str | None
    ) -> None:
        """Send a reset link, if the address belongs to an account.

        Returns None either way. The endpoint answers 202 regardless, because
        a different answer for a missing account turns this into an oracle for
        "does this person have an account here", which is exactly the question
        credential stuffing wants answered.
        """
        settings = get_settings()
        user = await self._users.get_by_email(email)
        await self._auth_logs.record(
            event=AuthEvent.PASSWORD_RESET_REQUESTED,
            user_id=user.uuid if user else None,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        if user is None:
            await self._session.commit()
            logger.info("password reset requested for unknown address")
            return

        raw = await self._issue(
            user=user,
            purpose=VerificationPurpose.PASSWORD_RESET,
            ttl=timedelta(minutes=settings.password_reset_token_ttl_minutes),
            ip_address=ip_address,
        )
        await self._session.commit()
        self._queue(
            user.email,
            password_reset_email(
                name=user.name,
                base_url=settings.frontend_base_url,
                token=raw,
                ttl_minutes=settings.password_reset_token_ttl_minutes,
            ),
        )

    async def confirm_password_reset(
        self,
        *,
        token: str,
        new_password: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        """Set a new password and end every existing session."""
        row = await self._tokens.get_usable(
            token_hash=hash_token(token),
            purpose=VerificationPurpose.PASSWORD_RESET,
        )
        if row is None:
            raise InvalidVerificationTokenError

        user = await self._users.get_by_id(row.user_id)
        if user is None:
            raise InvalidVerificationTokenError

        user.password_hash = hash_password(new_password)
        self._tokens.mark_used(row)
        # Whoever asked for this reset may have done so because someone else
        # had the account. Leaving old sessions alive would hand it back.
        revoked = await self._refresh_tokens.revoke_all_for_user(user.uuid)
        await self._auth_logs.record(
            event=AuthEvent.PASSWORD_RESET_COMPLETED,
            user_id=user.uuid,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._session.commit()
        logger.info(
            "password reset completed",
            extra={"user_id": str(user.uuid), "sessions_revoked": revoked},
        )

    # --------------------------------------------------------- verification
    async def send_email_verification(
        self, *, user: User, ip_address: str | None = None
    ) -> None:
        """Issue and queue a verification link. No-op if already verified."""
        if user.email_verified_at is not None:
            return
        settings = get_settings()
        raw = await self._issue(
            user=user,
            purpose=VerificationPurpose.EMAIL_VERIFICATION,
            ttl=timedelta(hours=settings.email_verification_token_ttl_hours),
            ip_address=ip_address,
        )
        await self._auth_logs.record(
            event=AuthEvent.EMAIL_VERIFICATION_SENT,
            user_id=user.uuid,
            email=user.email,
            ip_address=ip_address,
            user_agent=None,
        )
        await self._session.commit()
        self._queue(
            user.email,
            email_verification_email(
                name=user.name,
                base_url=settings.frontend_base_url,
                token=raw,
                ttl_hours=settings.email_verification_token_ttl_hours,
            ),
        )

    async def confirm_email_verification(
        self, *, token: str, ip_address: str | None, user_agent: str | None
    ) -> User:
        """Mark the address as proven."""
        row = await self._tokens.get_usable(
            token_hash=hash_token(token),
            purpose=VerificationPurpose.EMAIL_VERIFICATION,
        )
        if row is None:
            raise InvalidVerificationTokenError

        user = await self._users.get_by_id(row.user_id)
        if user is None:
            raise InvalidVerificationTokenError

        user.email_verified_at = datetime.now(UTC)
        self._tokens.mark_used(row)
        await self._auth_logs.record(
            event=AuthEvent.EMAIL_VERIFIED,
            user_id=user.uuid,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._session.commit()
        return user

    # -------------------------------------------------------------- helpers
    async def _issue(
        self,
        *,
        user: User,
        purpose: VerificationPurpose,
        ttl: timedelta,
        ip_address: str | None,
    ) -> str:
        """Mint one token, invalidating any outstanding one of the same kind.

        Returns the raw value, which exists only here and in the email. What
        goes to the database is its SHA-256 hash.
        """
        await self._tokens.invalidate_outstanding(user_id=user.uuid, purpose=purpose)
        raw = secrets.token_urlsafe(_TOKEN_BYTES)
        self._tokens.add(
            user_id=user.uuid,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + ttl,
            requested_ip=ip_address,
        )
        return raw

    def _queue(self, to: str, email: RenderedEmail) -> None:
        self._send_email(to=to, subject=email.subject, text=email.text, html=email.html)


def queue_via_celery(*, to: str, subject: str, text: str, html: str | None) -> None:
    """Default sender: hand the message to the worker and return.

    Imported lazily for the same reason the other task call sites do it:
    pulling the Celery task graph at module import time creates a cycle that
    breaks the API router.
    """
    from app.infrastructure.celery.tasks.email import send_email

    send_email.delay(to=to, subject=subject, text=text, html=html)
