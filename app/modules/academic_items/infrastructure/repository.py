"""Persistence access for academic items (soft-delete aware)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academic_items.infrastructure.models import AcademicItem


class AcademicItemRepository:
    """Data-access layer for the academic_items table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, item: AcademicItem) -> None:
        """Stage a new item for insertion."""
        self._session.add(item)

    async def get_by_id(self, item_id: UUID, user_id: UUID) -> AcademicItem | None:
        """Return a non-deleted item by id, scoped to its owner."""
        stmt = select(AcademicItem).where(
            AcademicItem.uuid == item_id,
            AcademicItem.user_id == user_id,
            AcademicItem.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_module(
        self, module_id: UUID, user_id: UUID, *, limit: int, offset: int
    ) -> list[AcademicItem]:
        """Return a module's non-deleted items, most recent first."""
        stmt = (
            select(AcademicItem)
            .where(
                AcademicItem.module_id == module_id,
                AcademicItem.user_id == user_id,
                AcademicItem.deleted_at.is_(None),
            )
            .order_by(AcademicItem.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
