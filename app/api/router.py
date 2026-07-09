"""Top-level API router aggregating all module routers."""

from fastapi import APIRouter

from app.modules.academic_item_categories.presentation.router import (
    categories_router,
    types_router,
)
from app.modules.academic_items.presentation.router import (
    router as academic_items_router,
)
from app.modules.ai.presentation.router import router as ai_router
from app.modules.audit.presentation.router import router as audit_router
from app.modules.auth.presentation.router import router as auth_router
from app.modules.catalogs.presentation.router import (
    colors_router,
    icons_router,
)
from app.modules.documents.presentation.router import (
    router as documents_router,
)
from app.modules.generation.presentation.router import (
    router as generation_router,
)
from app.modules.plan_modules.presentation.router import router as modules_router
from app.modules.rag.presentation.router import router as rag_router
from app.modules.subjects.presentation.router import router as subjects_router
from app.modules.teaching_plans.presentation.router import router as plans_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(subjects_router)
api_router.include_router(plans_router)
api_router.include_router(modules_router)
api_router.include_router(academic_items_router)
api_router.include_router(categories_router)
api_router.include_router(types_router)
api_router.include_router(icons_router)
api_router.include_router(colors_router)
api_router.include_router(documents_router)
api_router.include_router(rag_router)
api_router.include_router(ai_router)
api_router.include_router(audit_router)
api_router.include_router(generation_router)
