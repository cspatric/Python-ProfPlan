"""Use cases for reading and clearing a user's notifications."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.domain.exceptions import NotificationNotFoundError
from app.modules.notifications.infrastructure.models import Notification
from app.modules.notifications.infrastructure.repository import (
    NotificationRepository,
)


@dataclass(frozen=True, slots=True)
class NotificationPage:
    """A page of notifications, and how many are still unread.

    The two travel together because the bell needs both to draw itself once —
    the list to fill the panel and the count for the badge — and asking twice
    would put a second round trip in front of a menu that opens on a click.
    """

    items: list[Notification]
    unread: int


class NotificationService:
    """Lists a user's notifications and marks them read."""

    def __init__(self, session: AsyncSession, repo: NotificationRepository) -> None:
        self._session = session
        self._repo = repo

    async def page(
        self, *, user_id: UUID, limit: int = 20, offset: int = 0
    ) -> NotificationPage:
        """The most recent notifications, plus the unread count."""
        return NotificationPage(
            items=await self._repo.list_for_user(user_id, limit=limit, offset=offset),
            unread=await self._repo.unread_count(user_id),
        )

    async def mark_read(self, *, user_id: UUID, notification_id: UUID) -> None:
        """Mark one as read. Idempotent: reading it twice is not an error."""
        if not await self._repo.mark_read(notification_id, user_id):
            raise NotificationNotFoundError
        await self._session.commit()

    async def mark_all_read(self, *, user_id: UUID) -> int:
        """Mark everything unread as read; returns how many changed."""
        changed = await self._repo.mark_all_read(user_id)
        await self._session.commit()
        return changed
