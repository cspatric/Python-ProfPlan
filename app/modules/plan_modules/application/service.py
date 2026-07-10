"""Plan-module use cases (CRUD scoped to the owner)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academic_items.infrastructure.models import AcademicItem
from app.modules.audit.application.recorder import (
    AuditRecorder,
    entity_snapshot,
    jsonable,
)
from app.modules.audit.domain.entities import AuditAction
from app.modules.plan_modules.domain.exceptions import (
    InvalidPlanError,
    ModuleNotFoundError,
)
from app.modules.plan_modules.infrastructure.models import Module
from app.modules.plan_modules.infrastructure.repository import ModuleRepository
from app.modules.teaching_plans.infrastructure.repository import PlanRepository
from app.shared.db.soft_delete import cascade_soft_delete

_ENTITY = "module"


class ModuleService:
    """Coordinates module operations for a given user."""

    def __init__(
        self,
        session: AsyncSession,
        repository: ModuleRepository,
        plans: PlanRepository,
        audit: AuditRecorder,
    ) -> None:
        self._session = session
        self._repo = repository
        self._plans = plans
        self._audit = audit

    async def _ensure_plan_owned(self, plan_id: UUID, user_id: UUID) -> None:
        if await self._plans.get_by_id(plan_id, user_id) is None:
            raise InvalidPlanError

    async def create(self, *, user_id: UUID, data: dict[str, Any]) -> Module:
        """Create a module under a plan owned by the user."""
        await self._ensure_plan_owned(data["plan_id"], user_id)
        module = Module(user_id=user_id, created_by=user_id, **data)
        self._repo.add(module)
        await self._session.flush()
        self._audit.record(
            action=AuditAction.CREATE,
            entity=_ENTITY,
            entity_id=module.uuid,
            changes=entity_snapshot(module),
        )
        await self._session.commit()
        await self._session.refresh(module)
        return module

    async def list(
        self, *, user_id: UUID, plan_id: UUID, limit: int, offset: int
    ) -> list[Module]:
        """List modules of a plan owned by the user."""
        await self._ensure_plan_owned(plan_id, user_id)
        return await self._repo.list_by_plan(
            plan_id, user_id, limit=limit, offset=offset
        )

    async def get(self, *, user_id: UUID, module_id: UUID) -> Module:
        """Return a single module or raise if not found."""
        module = await self._repo.get_by_id(module_id, user_id)
        if module is None:
            raise ModuleNotFoundError
        return module

    async def update(
        self, *, user_id: UUID, module_id: UUID, data: dict[str, Any]
    ) -> Module:
        """Update mutable fields of a module."""
        module = await self.get(user_id=user_id, module_id=module_id)
        if "plan_id" in data:
            await self._ensure_plan_owned(data["plan_id"], user_id)
        changes = {
            field: {"old": jsonable(getattr(module, field)), "new": jsonable(value)}
            for field, value in data.items()
        }
        for field, value in data.items():
            setattr(module, field, value)
        self._audit.record(
            action=AuditAction.UPDATE,
            entity=_ENTITY,
            entity_id=module.uuid,
            changes=changes,
        )
        await self._session.commit()
        await self._session.refresh(module)
        return module

    async def delete(self, *, user_id: UUID, module_id: UUID) -> None:
        """Soft-delete a module and cascade to its academic items."""
        module = await self.get(user_id=user_id, module_id=module_id)
        self._audit.record(
            action=AuditAction.DELETE,
            entity=_ENTITY,
            entity_id=module.uuid,
            changes=entity_snapshot(module),
        )
        now = datetime.now(UTC)
        module.deleted_at = now

        await cascade_soft_delete(
            self._session, AcademicItem, AcademicItem.module_id == module.uuid, now
        )

        await self._session.commit()
