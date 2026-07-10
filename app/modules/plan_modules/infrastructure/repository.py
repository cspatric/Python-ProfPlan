"""Persistence access for plan modules."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.plan_modules.infrastructure.models import Module


class ModuleRepository:
    """Data-access layer for the modules table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, module: Module) -> None:
        """Stage a new module for insertion."""
        self._session.add(module)

    async def get_by_id(self, module_id: UUID, user_id: UUID) -> Module | None:
        """Return a non-deleted module by id, scoped to its owner."""
        stmt = select(Module).where(
            Module.uuid == module_id,
            Module.user_id == user_id,
            Module.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_plan(
        self, plan_id: UUID, user_id: UUID, *, limit: int, offset: int
    ) -> list[Module]:
        """Return a plan's non-deleted modules, ordered by start date."""
        stmt = (
            select(Module)
            .where(
                Module.plan_id == plan_id,
                Module.user_id == user_id,
                Module.deleted_at.is_(None),
            )
            .order_by(Module.start_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
