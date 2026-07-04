"""Persistence access for teaching plans."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.teaching_plans.infrastructure.models import Plan


class PlanRepository:
    """Data-access layer for the plans table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, plan: Plan) -> None:
        """Stage a new plan for insertion."""
        self._session.add(plan)

    async def get_by_id(self, plan_id: UUID, user_id: UUID) -> Plan | None:
        """Return a plan by id, scoped to its owner."""
        stmt = select(Plan).where(
            Plan.uuid == plan_id,
            Plan.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> list[Plan]:
        """Return the user's plans, most recent first."""
        stmt = (
            select(Plan)
            .where(Plan.user_id == user_id)
            .order_by(Plan.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, plan: Plan) -> None:
        """Delete a plan."""
        await self._session.delete(plan)
