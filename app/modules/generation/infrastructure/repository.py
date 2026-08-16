"""Persistence access for plan-generation runs and their items."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academic_items.infrastructure.models import AcademicItem
from app.modules.ai.domain.usage import UsageLedger
from app.modules.generation.domain.entities import (
    GenerationItemStatus,
    GenerationRunStatus,
)
from app.modules.generation.infrastructure.models import (
    PlanGeneration,
    PlanGenerationModelUsage,
)
from app.modules.users.infrastructure.models import User


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

    async def spend_since(self, user_id: UUID, since: datetime) -> Decimal:
        """What this account has spent on the AI since `since`, in USD.

        Summed from the runs rather than kept as a running total on the user:
        a counter that is incremented in two places drifts, and this is the
        number that decides whether somebody can work today.
        """
        total = await self._session.scalar(
            select(func.coalesce(func.sum(PlanGeneration.llm_cost_usd), 0)).where(
                PlanGeneration.user_id == user_id,
                PlanGeneration.created_at >= since,
            )
        )
        return Decimal(total or 0)

    async def spend_by_user_since(
        self, since: datetime
    ) -> list[tuple[UUID, str, int, int, Decimal]]:
        """(user id, email, runs, tokens, USD) for every account, dearest first."""
        rows = await self._session.execute(
            select(
                User.uuid,
                User.email,
                func.count(PlanGeneration.uuid),
                func.coalesce(
                    func.sum(
                        PlanGeneration.llm_input_tokens
                        + PlanGeneration.llm_output_tokens
                    ),
                    0,
                ),
                func.coalesce(func.sum(PlanGeneration.llm_cost_usd), 0),
            )
            .join(User, User.uuid == PlanGeneration.user_id)
            .where(PlanGeneration.created_at >= since)
            .group_by(User.uuid, User.email)
            .order_by(func.coalesce(func.sum(PlanGeneration.llm_cost_usd), 0).desc())
        )
        return [tuple(row) for row in rows.all()]

    async def add_usage(self, generation_id: UUID, ledger: UsageLedger) -> None:
        """Add one scope's LLM usage to a run's running total.

        The addition happens in the database, not in Python. A dozen item
        workers finish at the same time, and read-modify-write in the
        application would quietly drop most of their numbers, which is the
        worst possible failure for a cost report: it under-reports, and
        under-reporting looks like good news.

        Money is passed as Decimal rather than float, so the value that reaches
        a Numeric column is the one that was computed.
        """
        if ledger.calls == 0:
            return

        # Per model first, as an upsert that adds. Several workers land here at
        # the same moment, each carrying its own model's share, and adding in
        # the database is the only way none of them is lost.
        for model, used in ledger.by_model.items():
            insert = pg_insert(PlanGenerationModelUsage).values(
                generation_id=generation_id,
                model=model[:128],
                calls=used.calls,
                input_tokens=used.input_tokens,
                output_tokens=used.output_tokens,
                cost_usd=Decimal(str(used.cost_usd)),
            )
            await self._session.execute(
                insert.on_conflict_do_update(
                    index_elements=["generation_id", "model"],
                    set_={
                        "calls": PlanGenerationModelUsage.calls + insert.excluded.calls,
                        "input_tokens": (
                            PlanGenerationModelUsage.input_tokens
                            + insert.excluded.input_tokens
                        ),
                        "output_tokens": (
                            PlanGenerationModelUsage.output_tokens
                            + insert.excluded.output_tokens
                        ),
                        "cost_usd": (
                            PlanGenerationModelUsage.cost_usd + insert.excluded.cost_usd
                        ),
                    },
                )
            )

        await self._session.execute(
            update(PlanGeneration)
            .where(PlanGeneration.uuid == generation_id)
            .values(
                llm_calls=PlanGeneration.llm_calls + ledger.calls,
                llm_input_tokens=(
                    PlanGeneration.llm_input_tokens + ledger.input_tokens
                ),
                llm_output_tokens=(
                    PlanGeneration.llm_output_tokens + ledger.output_tokens
                ),
                llm_cost_usd=(
                    PlanGeneration.llm_cost_usd + Decimal(str(ledger.cost_usd))
                ),
            )
        )

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
