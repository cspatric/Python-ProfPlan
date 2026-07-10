"""Persistence access for the icon and color catalogs (global)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalogs.infrastructure.models import Color, Icon


class IconRepository:
    """Data-access layer for icons."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, icon: Icon) -> None:
        self._session.add(icon)

    async def get_by_id(self, icon_id: UUID) -> Icon | None:
        result = await self._session.execute(
            select(Icon).where(Icon.uuid == icon_id, Icon.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list(self, *, limit: int, offset: int) -> list[Icon]:
        stmt = (
            select(Icon)
            .where(Icon.deleted_at.is_(None))
            .order_by(Icon.name.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ColorRepository:
    """Data-access layer for colors."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, color: Color) -> None:
        self._session.add(color)

    async def get_by_id(self, color_id: UUID) -> Color | None:
        result = await self._session.execute(
            select(Color).where(Color.uuid == color_id, Color.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list(self, *, limit: int, offset: int) -> list[Color]:
        stmt = (
            select(Color)
            .where(Color.deleted_at.is_(None))
            .order_by(Color.name.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
