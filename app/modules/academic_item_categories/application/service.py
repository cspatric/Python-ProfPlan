"""Academic item category use cases (global catalogs)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academic_item_categories.domain.exceptions import (
    CategoryNotFoundError,
    CategoryTypeNotFoundError,
    InvalidCategoryError,
)
from app.modules.academic_item_categories.infrastructure.models import (
    AcademicItemCategory,
    AcademicItemCategoryType,
)
from app.modules.academic_item_categories.infrastructure.repository import (
    CategoryRepository,
    CategoryTypeRepository,
)


class CategoryService:
    """CRUD for academic item categories."""

    def __init__(self, session: AsyncSession, repository: CategoryRepository) -> None:
        self._session = session
        self._repo = repository

    async def create(self, *, data: dict[str, Any]) -> AcademicItemCategory:
        category = AcademicItemCategory(**data)
        self._repo.add(category)
        await self._session.commit()
        await self._session.refresh(category)
        return category

    async def list(self, *, limit: int, offset: int) -> list[AcademicItemCategory]:
        return await self._repo.list(limit=limit, offset=offset)

    async def get(self, *, category_id: UUID) -> AcademicItemCategory:
        category = await self._repo.get_by_id(category_id)
        if category is None:
            raise CategoryNotFoundError
        return category

    async def update(
        self, *, category_id: UUID, data: dict[str, Any]
    ) -> AcademicItemCategory:
        category = await self.get(category_id=category_id)
        for field, value in data.items():
            setattr(category, field, value)
        await self._session.commit()
        await self._session.refresh(category)
        return category

    async def delete(self, *, category_id: UUID) -> None:
        category = await self.get(category_id=category_id)
        category.deleted_at = datetime.now(UTC)
        await self._session.commit()


class CategoryTypeService:
    """CRUD for academic item category types."""

    def __init__(
        self,
        session: AsyncSession,
        repository: CategoryTypeRepository,
        categories: CategoryRepository,
    ) -> None:
        self._session = session
        self._repo = repository
        self._categories = categories

    async def _ensure_category_exists(self, category_id: UUID) -> None:
        if await self._categories.get_by_id(category_id) is None:
            raise InvalidCategoryError

    async def create(self, *, data: dict[str, Any]) -> AcademicItemCategoryType:
        await self._ensure_category_exists(data["academic_item_category_id"])
        category_type = AcademicItemCategoryType(**data)
        self._repo.add(category_type)
        await self._session.commit()
        await self._session.refresh(category_type)
        return category_type

    async def list(
        self, *, category_id: UUID | None, limit: int, offset: int
    ) -> list[AcademicItemCategoryType]:
        return await self._repo.list(
            category_id=category_id, limit=limit, offset=offset
        )

    async def get(self, *, type_id: UUID) -> AcademicItemCategoryType:
        category_type = await self._repo.get_by_id(type_id)
        if category_type is None:
            raise CategoryTypeNotFoundError
        return category_type

    async def update(
        self, *, type_id: UUID, data: dict[str, Any]
    ) -> AcademicItemCategoryType:
        category_type = await self.get(type_id=type_id)
        if "academic_item_category_id" in data:
            await self._ensure_category_exists(data["academic_item_category_id"])
        for field, value in data.items():
            setattr(category_type, field, value)
        await self._session.commit()
        await self._session.refresh(category_type)
        return category_type

    async def delete(self, *, type_id: UUID) -> None:
        category_type = await self.get(type_id=type_id)
        category_type.deleted_at = datetime.now(UTC)
        await self._session.commit()
