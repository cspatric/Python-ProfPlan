"""Top-level API router aggregating all module routers."""

from fastapi import APIRouter

from app.modules.auth.presentation.router import router as auth_router
from app.modules.subjects.presentation.router import router as subjects_router
from app.modules.teaching_plans.presentation.router import router as plans_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(subjects_router)
api_router.include_router(plans_router)
