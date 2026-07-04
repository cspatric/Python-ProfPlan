"""Unit tests for category/category-type services using in-memory fakes."""

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.academic_item_categories.application.service import (
    CategoryService,
    CategoryTypeService,
)
from app.modules.academic_item_categories.domain.exceptions import (
    CategoryNotFoundError,
    CategoryTypeNotFoundError,
    InvalidCategoryError,
)
from app.modules.academic_item_categories.infrastructure.models import (
    AcademicItemCategory,
    AcademicItemCategoryType,
)


class FakeSession:
    async def commit(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass


class FakeCategoryRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, AcademicItemCategory] = {}

    def add(self, category: AcademicItemCategory) -> None:
        if category.uuid is None:
            category.uuid = uuid4()
        self.items[category.uuid] = category

    async def get_by_id(self, category_id: UUID) -> AcademicItemCategory | None:
        return self.items.get(category_id)

    async def list(self, *, limit: int, offset: int) -> list[AcademicItemCategory]:
        return list(self.items.values())[offset : offset + limit]

    async def delete(self, category: AcademicItemCategory) -> None:
        self.items.pop(category.uuid, None)


class FakeCategoryTypeRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, AcademicItemCategoryType] = {}

    def add(self, category_type: AcademicItemCategoryType) -> None:
        if category_type.uuid is None:
            category_type.uuid = uuid4()
        self.items[category_type.uuid] = category_type

    async def get_by_id(self, type_id: UUID) -> AcademicItemCategoryType | None:
        return self.items.get(type_id)

    async def list(
        self, *, category_id: UUID | None, limit: int, offset: int
    ) -> list[AcademicItemCategoryType]:
        values = [
            t
            for t in self.items.values()
            if category_id is None or t.academic_item_category_id == category_id
        ]
        return values[offset : offset + limit]

    async def delete(self, category_type: AcademicItemCategoryType) -> None:
        self.items.pop(category_type.uuid, None)


def _category_data() -> dict[str, Any]:
    return {"name": "Evaluations", "icon_id": None}


# --------------------------------------------------------------------------- #
# CategoryService
# --------------------------------------------------------------------------- #
async def test_create_and_get_category() -> None:
    repo = FakeCategoryRepository()
    service = CategoryService(FakeSession(), repo)

    created = await service.create(data=_category_data())
    fetched = await service.get(category_id=created.uuid)

    assert fetched.uuid == created.uuid
    assert fetched.name == "Evaluations"


async def test_get_missing_category_raises() -> None:
    service = CategoryService(FakeSession(), FakeCategoryRepository())
    with pytest.raises(CategoryNotFoundError):
        await service.get(category_id=uuid4())


async def test_update_and_delete_category() -> None:
    repo = FakeCategoryRepository()
    service = CategoryService(FakeSession(), repo)
    created = await service.create(data=_category_data())

    updated = await service.update(category_id=created.uuid, data={"name": "Tests"})
    assert updated.name == "Tests"

    await service.delete(category_id=created.uuid)
    assert created.uuid not in repo.items


# --------------------------------------------------------------------------- #
# CategoryTypeService
# --------------------------------------------------------------------------- #
def make_type_service() -> tuple[
    CategoryTypeService, FakeCategoryRepository, FakeCategoryTypeRepository
]:
    categories = FakeCategoryRepository()
    types = FakeCategoryTypeRepository()
    service = CategoryTypeService(FakeSession(), types, categories)
    return service, categories, types


async def test_create_type_with_valid_category() -> None:
    service, categories, _ = make_type_service()
    category = AcademicItemCategory(uuid=uuid4(), name="Evaluations")
    categories.add(category)

    created = await service.create(
        data={
            "academic_item_category_id": category.uuid,
            "name": "Exam",
            "icon_id": None,
        }
    )
    assert created.academic_item_category_id == category.uuid


async def test_create_type_with_invalid_category_raises() -> None:
    service, _, _ = make_type_service()
    with pytest.raises(InvalidCategoryError):
        await service.create(
            data={
                "academic_item_category_id": uuid4(),
                "name": "Exam",
                "icon_id": None,
            }
        )


async def test_get_missing_type_raises() -> None:
    service, _, _ = make_type_service()
    with pytest.raises(CategoryTypeNotFoundError):
        await service.get(type_id=uuid4())
