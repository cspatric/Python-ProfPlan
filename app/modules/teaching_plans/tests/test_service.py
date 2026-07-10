"""Unit tests for PlanService using in-memory fakes."""

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.teaching_plans.application.service import PlanService
from app.modules.teaching_plans.domain.exceptions import (
    InvalidSubjectError,
    PlanNotFoundError,
)
from app.modules.teaching_plans.infrastructure.models import Plan


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


class FakePlanRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Plan] = {}

    def add(self, plan: Plan) -> None:
        if plan.uuid is None:
            plan.uuid = uuid4()
        plan.created_at = plan.updated_at = datetime.now(UTC)
        self.items[plan.uuid] = plan

    async def get_by_id(self, plan_id: UUID, user_id: UUID) -> Plan | None:
        plan = self.items.get(plan_id)
        if plan is None or plan.user_id != user_id or plan.deleted_at:
            return None
        return plan

    async def list_by_user(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> list[Plan]:
        owned = [
            p for p in self.items.values() if p.user_id == user_id and not p.deleted_at
        ]
        return owned[offset : offset + limit]


class FakeSubjectRepository:
    def __init__(self, owned: set[tuple[UUID, UUID]]) -> None:
        self._owned = owned

    async def get_by_id(self, subject_id: UUID, user_id: UUID) -> object | None:
        return object() if (subject_id, user_id) in self._owned else None


def _plan_data(subject_id: UUID) -> dict[str, Any]:
    return {
        "subject_id": subject_id,
        "starts_at": date(2026, 8, 1),
        "ends_at": date(2026, 12, 15),
        "class_duration": 50,
        "class_per_week": 2,
        "total_weight": None,
        "academic_items_id": None,
    }


def make_service(
    owned: set[tuple[UUID, UUID]],
) -> tuple[PlanService, FakePlanRepository]:
    repo = FakePlanRepository()
    service = PlanService(
        FakeSession(), repo, FakeSubjectRepository(owned), FakeAuditRecorder()
    )
    return service, repo


async def test_create_with_owned_subject() -> None:
    user_id, subject_id = uuid4(), uuid4()
    service, repo = make_service({(subject_id, user_id)})

    plan = await service.create(user_id=user_id, data=_plan_data(subject_id))

    assert plan.uuid in repo.items
    assert plan.user_id == user_id
    assert plan.subject_id == subject_id


async def test_create_with_unowned_subject_raises() -> None:
    user_id, subject_id = uuid4(), uuid4()
    service, _ = make_service(set())

    with pytest.raises(InvalidSubjectError):
        await service.create(user_id=user_id, data=_plan_data(subject_id))


async def test_get_missing_raises() -> None:
    service, _ = make_service(set())
    with pytest.raises(PlanNotFoundError):
        await service.get(user_id=uuid4(), plan_id=uuid4())


async def test_update_changes_fields() -> None:
    user_id, subject_id = uuid4(), uuid4()
    service, _ = make_service({(subject_id, user_id)})
    created = await service.create(user_id=user_id, data=_plan_data(subject_id))

    updated = await service.update(
        user_id=user_id, plan_id=created.uuid, data={"class_per_week": 4}
    )
    assert updated.class_per_week == 4


async def test_update_to_unowned_subject_raises() -> None:
    user_id, subject_id = uuid4(), uuid4()
    service, _ = make_service({(subject_id, user_id)})
    created = await service.create(user_id=user_id, data=_plan_data(subject_id))

    with pytest.raises(InvalidSubjectError):
        await service.update(
            user_id=user_id,
            plan_id=created.uuid,
            data={"subject_id": uuid4()},
        )


async def test_delete_soft_deletes_plan() -> None:
    user_id, subject_id = uuid4(), uuid4()
    service, repo = make_service({(subject_id, user_id)})
    created = await service.create(user_id=user_id, data=_plan_data(subject_id))

    await service.delete(user_id=user_id, plan_id=created.uuid)

    assert created.uuid in repo.items
    assert created.deleted_at is not None
    with pytest.raises(PlanNotFoundError):
        await service.get(user_id=user_id, plan_id=created.uuid)
