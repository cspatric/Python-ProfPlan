"""Academic item use cases (CRUD scoped to the owner, soft delete)."""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academic_items.application.handout_service import HandoutContext
from app.modules.academic_items.domain.exceptions import (
    AcademicItemNotFoundError,
    HandoutNotReadyError,
    InvalidModuleError,
)
from app.modules.academic_items.infrastructure.models import (
    AcademicItem,
    AcademicItemSource,
)
from app.modules.academic_items.infrastructure.repository import (
    AcademicItemRepository,
)
from app.modules.academic_items.infrastructure.source_repository import (
    AcademicItemSourceRepository,
)
from app.modules.plan_modules.infrastructure.repository import ModuleRepository


def _as_date(value: object) -> date | None:
    """Read a date out of the metadata JSON, which stores it as a datetime."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class AcademicItemService:
    """Coordinates academic item operations for a given user."""

    def __init__(
        self,
        session: AsyncSession,
        repository: AcademicItemRepository,
        modules: ModuleRepository,
        sources: AcademicItemSourceRepository,
    ) -> None:
        self._session = session
        self._repo = repository
        self._modules = modules
        self._sources = sources

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

    async def sources(
        self, *, user_id: UUID, item_id: UUID
    ) -> Sequence[tuple[AcademicItemSource, str | None]]:
        """The passages this item was written from, in the prompt's order.

        Ownership is checked by loading the item first: the sources quote the
        teacher's own uploaded material, so reaching them through an item id
        alone would be a way to read somebody else's documents.
        """
        await self.get(user_id=user_id, item_id=item_id)
        # Sequence, not list, in the annotation: this class has a method
        # called `list`, which shadows the builtin inside the class body and
        # makes `list[...]` a call on a function.
        return await self._sources.list_for_item(item_id)

    async def handout(self, *, user_id: UUID, item_id: UUID) -> HandoutContext:
        """The item, described the way the printable handout needs it."""
        item = await self.get(user_id=user_id, item_id=item_id)
        metadata = item.item_metadata or {}
        placement = await self._repo.context_for_handout(item_id, user_id)

        body = (item.content or {}).get("markdown") or ""
        if not body.strip():
            raise HandoutNotReadyError

        return HandoutContext(
            title=item.title,
            body=body,
            is_graded=bool(metadata.get("is_graded")),
            module_title=placement[0] if placement else None,
            subject_name=placement[1] if placement else None,
            starts_at=_as_date(metadata.get("starts_at")),
            ends_at=_as_date(metadata.get("ends_at")),
            description=item.description,
        )

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
