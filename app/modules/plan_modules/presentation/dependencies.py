"""FastAPI dependencies for the plan modules module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.plan_modules.application.service import ModuleService
from app.modules.plan_modules.infrastructure.repository import ModuleRepository
from app.modules.teaching_plans.infrastructure.repository import PlanRepository


def get_module_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ModuleService:
    """Build a ModuleService wired to the request-scoped session."""
    return ModuleService(session, ModuleRepository(session), PlanRepository(session))


ModuleServiceDep = Annotated[ModuleService, Depends(get_module_service)]
