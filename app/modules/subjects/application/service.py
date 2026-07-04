"""Subject use cases (CRUD scoped to the owner)."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.subjects.domain.exceptions import SubjectNotFoundError
from app.modules.subjects.infrastructure.models import Subject
from app.modules.subjects.infrastructure.repository import SubjectRepository


class SubjectService:
    """Coordinates subject operations for a given user."""

    def __init__(self, session: AsyncSession, repository: SubjectRepository) -> None:
        self._session = session
        self._repo = repository

    async def create(self, *, user_id: UUID, data: dict[str, Any]) -> Subject:
        """Create a subject owned by the user."""
        subject = Subject(user_id=user_id, **data)
        self._repo.add(subject)
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
        for field, value in data.items():
            setattr(subject, field, value)
        await self._session.commit()
        await self._session.refresh(subject)
        return subject

    async def delete(self, *, user_id: UUID, subject_id: UUID) -> None:
        """Delete a subject."""
        subject = await self.get(user_id=user_id, subject_id=subject_id)
        await self._repo.delete(subject)
        await self._session.commit()
