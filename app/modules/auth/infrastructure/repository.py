"""Persistence access for refresh-token sessions and auth logs."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.infrastructure.models import AuthEvent, AuthLog, RefreshToken


class RefreshTokenRepository:
    """Data-access layer for refresh-token sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip_address: str | None,
    ) -> RefreshToken:
        """Create a new session row with an explicit id."""
        session_row = RefreshToken(
            uuid=session_id,
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self._session.add(session_row)
        await self._session.flush()
        return session_row

    async def get_by_id(self, session_id: uuid.UUID) -> RefreshToken | None:
        """Return a session by its id."""
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.uuid == session_id)
        )
        return result.scalar_one_or_none()

    async def revoke(self, session_row: RefreshToken) -> None:
        """Revoke a single session."""
        session_row.revoked_at = datetime.now(UTC)
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke every active session of a user; returns affected count."""
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount or 0


class AuthLogRepository:
    """Data-access layer for the authentication audit trail."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        event: AuthEvent,
        user_id: uuid.UUID | None = None,
        email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Append an authentication event to the audit log."""
        self._session.add(
            AuthLog(
                event=event,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self._session.flush()
