"""FastAPI dependencies for the teaching plans module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.subjects.infrastructure.repository import SubjectRepository
from app.modules.teaching_plans.application.service import PlanService
from app.modules.teaching_plans.infrastructure.repository import PlanRepository


def get_plan_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PlanService:
    """Build a PlanService wired to the request-scoped session."""
    return PlanService(session, PlanRepository(session), SubjectRepository(session))


PlanServiceDep = Annotated[PlanService, Depends(get_plan_service)]
