"""Data access for notifications.

Every read is filtered by recipient here rather than in a caller. That is the
ownership invariant, and a notification is exactly the kind of row where
forgetting it would show one teacher what another teacher's plans are called.
"""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.infrastructure.models import Notification


class NotificationRepository:
    """Reads and writes notifications."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, notification: Notification) -> None:
        """Stage a row in the caller's transaction (no commit here)."""
        self._session.add(notification)

    async def list_for_user(
        self, user_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[Notification]:
        """This user's notifications, newest first."""
        result = await self._session.scalars(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.all())

    async def unread_count(self, user_id: UUID) -> int:
        """How many this user has not seen. Answers the badge."""
        return (
            await self._session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
        ) or 0

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> bool:
        """Mark one as read. False when it is not this user's, or not there.

        Already-read rows keep their original timestamp: `read_at IS NULL` in
        the filter makes this idempotent, so a double click does not move the
        moment the person actually saw it.
        """
        result = await self._session.execute(
            update(Notification)
            .where(
                Notification.uuid == notification_id,
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=func.now())
        )
        if result.rowcount:
            return True
        # Nothing updated: either it was already read (which is a success from
        # the caller's point of view) or it is not theirs (which is a 404).
        exists = await self._session.scalar(
            select(Notification.uuid).where(
                Notification.uuid == notification_id,
                Notification.user_id == user_id,
            )
        )
        return exists is not None

    async def mark_all_read(self, user_id: UUID) -> int:
        """Mark every unread one as read; returns how many were affected."""
        result = await self._session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=func.now())
        )
        return result.rowcount or 0
