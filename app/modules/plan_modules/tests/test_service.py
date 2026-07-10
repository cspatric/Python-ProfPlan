"""Unit tests for ModuleService using in-memory fakes."""

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.plan_modules.application.service import ModuleService
from app.modules.plan_modules.domain.exceptions import (
    InvalidPlanError,
    ModuleNotFoundError,
)
from app.modules.plan_modules.infrastructure.models import Module


class FakeCascadeResult:
    def scalars(self) -> "FakeCascadeResult":
        return self

    def all(self) -> list:
        return []


class FakeSession:
    async def commit(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def execute(self, *args: object, **kwargs: object) -> FakeCascadeResult:
        return FakeCascadeResult()


class FakeAuditRecorder:
    def record(self, **kwargs: object) -> None:
        pass


class FakeModuleRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Module] = {}

    def add(self, module: Module) -> None:
        if module.uuid is None:
            module.uuid = uuid4()
        module.created_at = module.updated_at = datetime.now(UTC)
        self.items[module.uuid] = module

    async def get_by_id(self, module_id: UUID, user_id: UUID) -> Module | None:
        module = self.items.get(module_id)
        if module is None or module.user_id != user_id or module.deleted_at:
            return None
        return module

    async def list_by_plan(
        self, plan_id: UUID, user_id: UUID, *, limit: int, offset: int
    ) -> list[Module]:
        owned = [
            m
            for m in self.items.values()
            if m.plan_id == plan_id and m.user_id == user_id and not m.deleted_at
        ]
        return owned[offset : offset + limit]


class FakePlanRepository:
    def __init__(self, owned: set[tuple[UUID, UUID]]) -> None:
        self._owned = owned

    async def get_by_id(self, plan_id: UUID, user_id: UUID) -> object | None:
        return object() if (plan_id, user_id) in self._owned else None


def _module_data(plan_id: UUID) -> dict[str, Any]:
    return {
        "plan_id": plan_id,
        "title": "Intro",
        "description": None,
        "start_at": date(2026, 8, 1),
        "ends_at": date(2026, 9, 1),
    }


def make_service(
    owned: set[tuple[UUID, UUID]],
) -> tuple[ModuleService, FakeModuleRepository]:
    repo = FakeModuleRepository()
    service = ModuleService(
        FakeSession(), repo, FakePlanRepository(owned), FakeAuditRecorder()
    )
    return service, repo


async def test_create_sets_owner_and_created_by() -> None:
    user_id, plan_id = uuid4(), uuid4()
    service, repo = make_service({(plan_id, user_id)})

    module = await service.create(user_id=user_id, data=_module_data(plan_id))

    assert module.uuid in repo.items
    assert module.user_id == user_id
    assert module.created_by == user_id
    assert module.plan_id == plan_id


async def test_create_with_unowned_plan_raises() -> None:
    user_id, plan_id = uuid4(), uuid4()
    service, _ = make_service(set())

    with pytest.raises(InvalidPlanError):
        await service.create(user_id=user_id, data=_module_data(plan_id))


async def test_get_missing_raises() -> None:
    service, _ = make_service(set())
    with pytest.raises(ModuleNotFoundError):
        await service.get(user_id=uuid4(), module_id=uuid4())


async def test_update_changes_fields() -> None:
    user_id, plan_id = uuid4(), uuid4()
    service, _ = make_service({(plan_id, user_id)})
    created = await service.create(user_id=user_id, data=_module_data(plan_id))

    updated = await service.update(
        user_id=user_id, module_id=created.uuid, data={"title": "New title"}
    )
    assert updated.title == "New title"


async def test_list_requires_owned_plan() -> None:
    service, _ = make_service(set())
    with pytest.raises(InvalidPlanError):
        await service.list(user_id=uuid4(), plan_id=uuid4(), limit=50, offset=0)


async def test_delete_soft_deletes_module() -> None:
    user_id, plan_id = uuid4(), uuid4()
    service, repo = make_service({(plan_id, user_id)})
    created = await service.create(user_id=user_id, data=_module_data(plan_id))

    await service.delete(user_id=user_id, module_id=created.uuid)

    assert created.uuid in repo.items
    assert created.deleted_at is not None
    with pytest.raises(ModuleNotFoundError):
        await service.get(user_id=user_id, module_id=created.uuid)
