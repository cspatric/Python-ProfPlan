"""Subject use cases (CRUD scoped to the owner)."""

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
from app.modules.documents.infrastructure.models import Document
from app.modules.plan_modules.infrastructure.models import Module
from app.modules.subjects.domain.exceptions import SubjectNotFoundError
from app.modules.subjects.infrastructure.models import Subject
from app.modules.subjects.infrastructure.repository import SubjectRepository
from app.modules.teaching_plans.infrastructure.models import Plan
from app.shared.db.soft_delete import cascade_soft_delete

_ENTITY = "subject"


class SubjectService:
    """Coordinates subject operations for a given user."""

    def __init__(
        self,
        session: AsyncSession,
        repository: SubjectRepository,
        audit: AuditRecorder,
    ) -> None:
        self._session = session
        self._repo = repository
        self._audit = audit

    async def create(self, *, user_id: UUID, data: dict[str, Any]) -> Subject:
        """Create a subject owned by the user."""
        subject = Subject(user_id=user_id, **data)
        self._repo.add(subject)
        await self._session.flush()
        self._audit.record(
            action=AuditAction.CREATE,
            entity=_ENTITY,
            entity_id=subject.uuid,
            changes=entity_snapshot(subject),
        )
        await self._session.commit()
        await self._session.refresh(subject)
        return subject

    async def list(self, *, user_id: UUID, limit: int, offset: int) -> list[Subject]:
        """List the user's subjects."""
        return await self._repo.list_by_user(user_id, limit=limit, offset=offset)

    async def get(self, *, user_id: UUID, subject_id: UUID) -> Subject:
        """Return a single subject or raise if not found."""
        subject = await self._repo.get_by_id(subject_id, user_id)
        if subject is None:
            raise SubjectNotFoundError
        return subject

    async def update(
        self, *, user_id: UUID, subject_id: UUID, data: dict[str, Any]
    ) -> Subject:
        """Update mutable fields of a subject."""
        subject = await self.get(user_id=user_id, subject_id=subject_id)
        changes = {
            field: {"old": jsonable(getattr(subject, field)), "new": jsonable(value)}
            for field, value in data.items()
        }
        for field, value in data.items():
            setattr(subject, field, value)
        self._audit.record(
            action=AuditAction.UPDATE,
            entity=_ENTITY,
            entity_id=subject.uuid,
            changes=changes,
        )
        await self._session.commit()
        await self._session.refresh(subject)
        return subject

    async def delete(self, *, user_id: UUID, subject_id: UUID) -> None:
        """Soft-delete a subject and cascade to its plans/modules/items/documents."""
        subject = await self.get(user_id=user_id, subject_id=subject_id)
        self._audit.record(
            action=AuditAction.DELETE,
            entity=_ENTITY,
            entity_id=subject.uuid,
            changes=entity_snapshot(subject),
        )
        now = datetime.now(UTC)
        subject.deleted_at = now

        plan_ids = await cascade_soft_delete(
            self._session, Plan, Plan.subject_id == subject.uuid, now
        )
        if plan_ids:
            module_ids = await cascade_soft_delete(
                self._session, Module, Module.plan_id.in_(plan_ids), now
            )
            if module_ids:
                await cascade_soft_delete(
                    self._session,
                    AcademicItem,
                    AcademicItem.module_id.in_(module_ids),
                    now,
                )
        await cascade_soft_delete(
            self._session, Document, Document.subject_id == subject.uuid, now
        )

        await self._session.commit()
