"""Persistence access for academic items (soft-delete aware)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academic_items.infrastructure.models import AcademicItem
from app.modules.plan_modules.infrastructure.models import Module
from app.modules.subjects.infrastructure.models import Subject
from app.modules.teaching_plans.infrastructure.models import Plan


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

    async def context_for_handout(
        self, item_id: UUID, user_id: UUID
    ) -> tuple[str, str] | None:
        """Return ``(module_title, subject_name)`` for an item the user owns.

        The handout's cover names where the activity sits, which lives two
        joins away. One query beats loading three services to read two strings.
        """
        stmt = (
            select(Module.title, Subject.name)
            .join(AcademicItem, AcademicItem.module_id == Module.uuid)
            .join(Plan, Module.plan_id == Plan.uuid)
            .join(Subject, Plan.subject_id == Subject.uuid)
            .where(
                AcademicItem.uuid == item_id,
                AcademicItem.user_id == user_id,
                AcademicItem.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        row = result.first()
        return (row[0], row[1]) if row else None

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
