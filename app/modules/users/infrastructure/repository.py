"""Persistence access for users."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.domain.entities import UserStatus
from app.modules.users.infrastructure.models import User


class UserRepository:
    """Data-access layer for the users table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        """Return an active (non-deleted) user by email, if any."""
        stmt = select(User).where(
            User.email == email.lower(),
            User.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Return an active (non-deleted) user by id, if any."""
        stmt = select(User).where(
            User.uuid == user_id,
            User.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, *, name: str, email: str, password_hash: str) -> User:
        """Persist a new user."""
        user = User(
            name=name,
            email=email.lower(),
            password_hash=password_hash,
            status=UserStatus.ACTIVE,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def mark_logged_in(self, user: User) -> None:
        """Update the last login timestamp."""
        user.last_login_at = datetime.now(UTC)
        await self._session.flush()
