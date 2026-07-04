"""FastAPI dependencies for the subjects module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.subjects.application.service import SubjectService
from app.modules.subjects.infrastructure.repository import SubjectRepository


def get_subject_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SubjectService:
    """Build a SubjectService wired to the request-scoped session."""
    return SubjectService(session, SubjectRepository(session))


SubjectServiceDep = Annotated[SubjectService, Depends(get_subject_service)]
