"""Unit tests for icon/color catalog services using in-memory fakes."""

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.catalogs.application.service import ColorService, IconService
from app.modules.catalogs.domain.exceptions import ColorNotFoundError, IconNotFoundError
from app.modules.catalogs.infrastructure.models import Color, Icon


class FakeSession:
    async def commit(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass


class FakeIconRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Icon] = {}

    def add(self, icon: Icon) -> None:
        if icon.uuid is None:
            icon.uuid = uuid4()
        self.items[icon.uuid] = icon

    async def get_by_id(self, icon_id: UUID) -> Icon | None:
        return self.items.get(icon_id)

    async def list(self, *, limit: int, offset: int) -> list[Icon]:
        return list(self.items.values())[offset : offset + limit]

    async def delete(self, icon: Icon) -> None:
        self.items.pop(icon.uuid, None)


class FakeColorRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Color] = {}

    def add(self, color: Color) -> None:
        if color.uuid is None:
            color.uuid = uuid4()
        self.items[color.uuid] = color

    async def get_by_id(self, color_id: UUID) -> Color | None:
        return self.items.get(color_id)

    async def list(self, *, limit: int, offset: int) -> list[Color]:
        return list(self.items.values())[offset : offset + limit]

    async def delete(self, color: Color) -> None:
        self.items.pop(color.uuid, None)


def _icon_data() -> dict[str, Any]:
    return {"name": "Mathematics", "file_path": "icons/mathematics.svg"}


def _color_data() -> dict[str, Any]:
    return {"name": "Pastel Pink", "hex_code": "#FFD1DC"}


# --------------------------------------------------------------------------- #
# IconService
# --------------------------------------------------------------------------- #
async def test_create_and_get_icon() -> None:
    repo = FakeIconRepository()
    service = IconService(FakeSession(), repo)

    created = await service.create(data=_icon_data())
    fetched = await service.get(icon_id=created.uuid)

    assert fetched.uuid == created.uuid
    assert fetched.name == "Mathematics"
    assert fetched.file_path == "icons/mathematics.svg"


async def test_get_missing_icon_raises() -> None:
    service = IconService(FakeSession(), FakeIconRepository())
    with pytest.raises(IconNotFoundError):
        await service.get(icon_id=uuid4())


async def test_update_and_delete_icon() -> None:
    repo = FakeIconRepository()
    service = IconService(FakeSession(), repo)
    created = await service.create(data=_icon_data())

    updated = await service.update(icon_id=created.uuid, data={"name": "Algebra"})
    assert updated.name == "Algebra"

    await service.delete(icon_id=created.uuid)
    assert created.uuid not in repo.items


# --------------------------------------------------------------------------- #
# ColorService
# --------------------------------------------------------------------------- #
async def test_create_and_get_color() -> None:
    repo = FakeColorRepository()
    service = ColorService(FakeSession(), repo)

    created = await service.create(data=_color_data())
    fetched = await service.get(color_id=created.uuid)

    assert fetched.uuid == created.uuid
    assert fetched.name == "Pastel Pink"
    assert fetched.hex_code == "#FFD1DC"


async def test_get_missing_color_raises() -> None:
    service = ColorService(FakeSession(), FakeColorRepository())
    with pytest.raises(ColorNotFoundError):
        await service.get(color_id=uuid4())


async def test_update_and_delete_color() -> None:
    repo = FakeColorRepository()
    service = ColorService(FakeSession(), repo)
    created = await service.create(data=_color_data())

    updated = await service.update(color_id=created.uuid, data={"name": "Pastel Rose"})
    assert updated.name == "Pastel Rose"

    await service.delete(color_id=created.uuid)
    assert created.uuid not in repo.items
