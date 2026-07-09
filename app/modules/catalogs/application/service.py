"""Icon and color catalog use cases (global catalogs)."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalogs.domain.exceptions import ColorNotFoundError, IconNotFoundError
from app.modules.catalogs.infrastructure.models import Color, Icon
from app.modules.catalogs.infrastructure.repository import (
    ColorRepository,
    IconRepository,
)


class IconService:
    """CRUD for icons."""

    def __init__(self, session: AsyncSession, repository: IconRepository) -> None:
        self._session = session
        self._repo = repository

    async def create(self, *, data: dict[str, Any]) -> Icon:
        icon = Icon(**data)
        self._repo.add(icon)
        await self._session.commit()
        await self._session.refresh(icon)
        return icon

    async def list(self, *, limit: int, offset: int) -> list[Icon]:
        return await self._repo.list(limit=limit, offset=offset)

    async def get(self, *, icon_id: UUID) -> Icon:
        icon = await self._repo.get_by_id(icon_id)
        if icon is None:
            raise IconNotFoundError
        return icon

    async def update(self, *, icon_id: UUID, data: dict[str, Any]) -> Icon:
        icon = await self.get(icon_id=icon_id)
        for field, value in data.items():
            setattr(icon, field, value)
        await self._session.commit()
        await self._session.refresh(icon)
        return icon

    async def delete(self, *, icon_id: UUID) -> None:
        icon = await self.get(icon_id=icon_id)
        await self._repo.delete(icon)
        await self._session.commit()


class ColorService:
    """CRUD for colors."""

    def __init__(self, session: AsyncSession, repository: ColorRepository) -> None:
        self._session = session
        self._repo = repository

    async def create(self, *, data: dict[str, Any]) -> Color:
        color = Color(**data)
        self._repo.add(color)
        await self._session.commit()
        await self._session.refresh(color)
        return color

    async def list(self, *, limit: int, offset: int) -> list[Color]:
        return await self._repo.list(limit=limit, offset=offset)

    async def get(self, *, color_id: UUID) -> Color:
        color = await self._repo.get_by_id(color_id)
        if color is None:
            raise ColorNotFoundError
        return color

    async def update(self, *, color_id: UUID, data: dict[str, Any]) -> Color:
        color = await self.get(color_id=color_id)
        for field, value in data.items():
            setattr(color, field, value)
        await self._session.commit()
        await self._session.refresh(color)
        return color

    async def delete(self, *, color_id: UUID) -> None:
        color = await self.get(color_id=color_id)
        await self._repo.delete(color)
        await self._session.commit()
