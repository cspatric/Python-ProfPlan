"""Unit tests for AcademicItemService using in-memory fakes."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.academic_items.application.service import AcademicItemService
from app.modules.academic_items.domain.exceptions import (
    AcademicItemNotFoundError,
    InvalidModuleError,
)
from app.modules.academic_items.infrastructure.models import AcademicItem


class FakeSession:
    async def commit(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass


class FakeItemRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, AcademicItem] = {}

    def add(self, item: AcademicItem) -> None:
        if item.uuid is None:
            item.uuid = uuid4()
        item.created_at = item.updated_at = datetime.now(UTC)
        self.items[item.uuid] = item

    async def get_by_id(self, item_id: UUID, user_id: UUID) -> AcademicItem | None:
        item = self.items.get(item_id)
        if item is None or item.user_id != user_id or item.deleted_at is not None:
            return None
        return item

    async def list_by_module(
        self, module_id: UUID, user_id: UUID, *, limit: int, offset: int
    ) -> list[AcademicItem]:
        owned = [
            i
            for i in self.items.values()
            if i.module_id == module_id
            and i.user_id == user_id
            and i.deleted_at is None
        ]
        return owned[offset : offset + limit]


class FakeModuleRepository:
    def __init__(self, owned: set[tuple[UUID, UUID]]) -> None:
        self._owned = owned

    async def get_by_id(self, module_id: UUID, user_id: UUID) -> object | None:
        return object() if (module_id, user_id) in self._owned else None


def _item_data(module_id: UUID) -> dict[str, Any]:
    return {
        "module_id": module_id,
        "item_category_id": None,
        "title": "Exam 1",
        "description": None,
        "content": {"questions": 3},
        "item_metadata": {"is_graded": True, "weight": 30},
    }


def make_service(
    owned: set[tuple[UUID, UUID]],
) -> tuple[AcademicItemService, FakeItemRepository]:
    repo = FakeItemRepository()
    service = AcademicItemService(FakeSession(), repo, FakeModuleRepository(owned))
    return service, repo


async def test_create_sets_owner_and_metadata() -> None:
    user_id, module_id = uuid4(), uuid4()
    service, repo = make_service({(module_id, user_id)})

    item = await service.create(user_id=user_id, data=_item_data(module_id))

    assert item.uuid in repo.items
    assert item.user_id == user_id
    assert item.created_by == user_id
    assert item.item_metadata == {"is_graded": True, "weight": 30}
    assert item.content == {"questions": 3}


async def test_create_with_unowned_module_raises() -> None:
    user_id, module_id = uuid4(), uuid4()
    service, _ = make_service(set())

    with pytest.raises(InvalidModuleError):
        await service.create(user_id=user_id, data=_item_data(module_id))


async def test_get_missing_raises() -> None:
    service, _ = make_service(set())
    with pytest.raises(AcademicItemNotFoundError):
        await service.get(user_id=uuid4(), item_id=uuid4())


async def test_update_changes_fields() -> None:
    user_id, module_id = uuid4(), uuid4()
    service, _ = make_service({(module_id, user_id)})
    created = await service.create(user_id=user_id, data=_item_data(module_id))

    updated = await service.update(
        user_id=user_id, item_id=created.uuid, data={"title": "Final Exam"}
    )
    assert updated.title == "Final Exam"


async def test_soft_delete_hides_item_but_keeps_row() -> None:
    user_id, module_id = uuid4(), uuid4()
    service, repo = make_service({(module_id, user_id)})
    created = await service.create(user_id=user_id, data=_item_data(module_id))

    await service.delete(user_id=user_id, item_id=created.uuid)

    assert repo.items[created.uuid].deleted_at is not None
    with pytest.raises(AcademicItemNotFoundError):
        await service.get(user_id=user_id, item_id=created.uuid)


async def test_list_requires_owned_module() -> None:
    service, _ = make_service(set())
    with pytest.raises(InvalidModuleError):
        await service.list(user_id=uuid4(), module_id=uuid4(), limit=50, offset=0)
