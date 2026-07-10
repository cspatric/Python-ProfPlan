"""Persistence access for academic item category catalogs (global)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academic_item_categories.infrastructure.models import (
    AcademicItemCategory,
    AcademicItemCategoryType,
)


class CategoryRepository:
    """Data-access layer for academic_item_category."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, category: AcademicItemCategory) -> None:
        self._session.add(category)

    async def get_by_id(self, category_id: UUID) -> AcademicItemCategory | None:
        result = await self._session.execute(
            select(AcademicItemCategory).where(
                AcademicItemCategory.uuid == category_id,
                AcademicItemCategory.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list(self, *, limit: int, offset: int) -> list[AcademicItemCategory]:
        stmt = (
            select(AcademicItemCategory)
            .where(AcademicItemCategory.deleted_at.is_(None))
            .order_by(AcademicItemCategory.name.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class CategoryTypeRepository:
    """Data-access layer for academic_item_category_types."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, category_type: AcademicItemCategoryType) -> None:
        self._session.add(category_type)

    async def get_by_id(self, type_id: UUID) -> AcademicItemCategoryType | None:
        result = await self._session.execute(
            select(AcademicItemCategoryType).where(
                AcademicItemCategoryType.uuid == type_id,
                AcademicItemCategoryType.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self, *, category_id: UUID | None, limit: int, offset: int
    ) -> list[AcademicItemCategoryType]:
        stmt = select(AcademicItemCategoryType).where(
            AcademicItemCategoryType.deleted_at.is_(None)
        )
        if category_id is not None:
            stmt = stmt.where(
                AcademicItemCategoryType.academic_item_category_id == category_id
            )
        stmt = (
            stmt.order_by(AcademicItemCategoryType.name.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
