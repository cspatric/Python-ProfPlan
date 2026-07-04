"""Academic item use cases (CRUD scoped to the owner, soft delete)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academic_items.domain.exceptions import (
    AcademicItemNotFoundError,
    InvalidModuleError,
)
from app.modules.academic_items.infrastructure.models import AcademicItem
from app.modules.academic_items.infrastructure.repository import (
    AcademicItemRepository,
)
from app.modules.plan_modules.infrastructure.repository import ModuleRepository


class AcademicItemService:
    """Coordinates academic item operations for a given user."""

    def __init__(
        self,
        session: AsyncSession,
        repository: AcademicItemRepository,
        modules: ModuleRepository,
    ) -> None:
        self._session = session
        self._repo = repository
        self._modules = modules

    async def _ensure_module_owned(self, module_id: UUID, user_id: UUID) -> None:
        if await self._modules.get_by_id(module_id, user_id) is None:
            raise InvalidModuleError

    async def create(self, *, user_id: UUID, data: dict[str, Any]) -> AcademicItem:
        """Create an item under a module owned by the user."""
        await self._ensure_module_owned(data["module_id"], user_id)
        item = AcademicItem(user_id=user_id, created_by=user_id, **data)
        self._repo.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def list(
        self, *, user_id: UUID, module_id: UUID, limit: int, offset: int
    ) -> list[AcademicItem]:
        """List items of a module owned by the user."""
        await self._ensure_module_owned(module_id, user_id)
        return await self._repo.list_by_module(
            module_id, user_id, limit=limit, offset=offset
        )

    async def get(self, *, user_id: UUID, item_id: UUID) -> AcademicItem:
        """Return a single item or raise if not found."""
        item = await self._repo.get_by_id(item_id, user_id)
        if item is None:
            raise AcademicItemNotFoundError
        return item

    async def update(
        self, *, user_id: UUID, item_id: UUID, data: dict[str, Any]
    ) -> AcademicItem:
        """Update mutable fields of an item."""
        item = await self.get(user_id=user_id, item_id=item_id)
        if "module_id" in data:
            await self._ensure_module_owned(data["module_id"], user_id)
        for field, value in data.items():
            setattr(item, field, value)
        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def delete(self, *, user_id: UUID, item_id: UUID) -> None:
        """Soft-delete an item (sets deleted_at)."""
        item = await self.get(user_id=user_id, item_id=item_id)
        item.deleted_at = datetime.now(UTC)
        await self._session.commit()
