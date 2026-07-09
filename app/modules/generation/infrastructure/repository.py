"""Persistence access for plan-generation runs and their items."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academic_items.infrastructure.models import AcademicItem
from app.modules.generation.domain.entities import (
    GenerationItemStatus,
    GenerationRunStatus,
)
from app.modules.generation.infrastructure.models import PlanGeneration


class GenerationRepository:
    """Data-access for plan_generation runs and their generated items."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- runs ---------------------------------------------------------------
    def add(self, run: PlanGeneration) -> None:
        self._session.add(run)

    async def get_by_id(
        self, generation_id: UUID, user_id: UUID
    ) -> PlanGeneration | None:
        """Return a run scoped to its owner."""
        stmt = select(PlanGeneration).where(
            PlanGeneration.uuid == generation_id,
            PlanGeneration.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_processing(self, generation_id: UUID) -> PlanGeneration | None:
        """Return a run by id without owner scoping (worker use)."""
        result = await self._session.execute(
            select(PlanGeneration).where(PlanGeneration.uuid == generation_id)
        )
        return result.scalar_one_or_none()

    # --- items (academic_items owned by a run) ------------------------------
    async def list_items(self, generation_id: UUID) -> list[AcademicItem]:
        """Return the items of a run, in creation order."""
        stmt = (
            select(AcademicItem)
            .where(
                AcademicItem.generation_id == generation_id,
                AcademicItem.deleted_at.is_(None),
            )
            .order_by(AcademicItem.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def item_for_processing(self, item_id: UUID) -> AcademicItem | None:
        """Return an academic item by id without owner scoping (worker use)."""
        result = await self._session.execute(
            select(AcademicItem).where(AcademicItem.uuid == item_id)
        )
        return result.scalar_one_or_none()

    async def item_status_counts(
        self, generation_id: UUID
    ) -> dict[GenerationItemStatus, int]:
        """Return how many items are in each status for a run."""
        items = await self.list_items(generation_id)
        counts: dict[GenerationItemStatus, int] = {}
        for item in items:
            if item.generation_status is not None:
                counts[item.generation_status] = (
                    counts.get(item.generation_status, 0) + 1
                )
        return counts

    def set_run_status(
        self,
        run: PlanGeneration,
        status: GenerationRunStatus,
        *,
        error: str | None = None,
    ) -> None:
        """Update a run's status in place (caller commits)."""
        run.status = status
        run.error = error
