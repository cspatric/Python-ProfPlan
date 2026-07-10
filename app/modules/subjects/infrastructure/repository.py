"""Persistence access for subjects."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.subjects.infrastructure.models import Subject


class SubjectRepository:
    """Data-access layer for the subjects table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, subject: Subject) -> None:
        """Stage a new subject for insertion."""
        self._session.add(subject)

    async def get_by_id(self, subject_id: UUID, user_id: UUID) -> Subject | None:
        """Return a non-deleted subject by id, scoped to its owner."""
        stmt = select(Subject).where(
            Subject.uuid == subject_id,
            Subject.user_id == user_id,
            Subject.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> list[Subject]:
        """Return the user's non-deleted subjects, most recent first."""
        stmt = (
            select(Subject)
            .where(Subject.user_id == user_id, Subject.deleted_at.is_(None))
            .order_by(Subject.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
