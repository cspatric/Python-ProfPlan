"""Teaching plan use cases (CRUD scoped to the owner)."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.subjects.infrastructure.repository import SubjectRepository
from app.modules.teaching_plans.domain.exceptions import (
    InvalidSubjectError,
    PlanNotFoundError,
)
from app.modules.teaching_plans.infrastructure.models import Plan
from app.modules.teaching_plans.infrastructure.repository import PlanRepository


class PlanService:
    """Coordinates plan operations for a given user."""

    def __init__(
        self,
        session: AsyncSession,
        repository: PlanRepository,
        subjects: SubjectRepository,
    ) -> None:
        self._session = session
        self._repo = repository
        self._subjects = subjects

    async def _ensure_subject_owned(
        self, subject_id: UUID, user_id: UUID
    ) -> None:
        if await self._subjects.get_by_id(subject_id, user_id) is None:
            raise InvalidSubjectError

    async def create(self, *, user_id: UUID, data: dict[str, Any]) -> Plan:
        """Create a plan owned by the user."""
        await self._ensure_subject_owned(data["subject_id"], user_id)
        plan = Plan(user_id=user_id, **data)
        self._repo.add(plan)
        await self._session.commit()
        await self._session.refresh(plan)
        return plan

    async def list(
        self, *, user_id: UUID, limit: int, offset: int
    ) -> list[Plan]:
        """List the user's plans."""
        return await self._repo.list_by_user(user_id, limit=limit, offset=offset)

    async def get(self, *, user_id: UUID, plan_id: UUID) -> Plan:
        """Return a single plan or raise if not found."""
        plan = await self._repo.get_by_id(plan_id, user_id)
        if plan is None:
            raise PlanNotFoundError
        return plan

    async def update(
        self, *, user_id: UUID, plan_id: UUID, data: dict[str, Any]
    ) -> Plan:
        """Update mutable fields of a plan."""
        plan = await self.get(user_id=user_id, plan_id=plan_id)
        if "subject_id" in data:
            await self._ensure_subject_owned(data["subject_id"], user_id)
        for field, value in data.items():
            setattr(plan, field, value)
        await self._session.commit()
        await self._session.refresh(plan)
        return plan

    async def delete(self, *, user_id: UUID, plan_id: UUID) -> None:
        """Delete a plan."""
        plan = await self.get(user_id=user_id, plan_id=plan_id)
        await self._repo.delete(plan)
        await self._session.commit()
