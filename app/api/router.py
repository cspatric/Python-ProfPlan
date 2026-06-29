"""Top-level API router aggregating all module routers."""

from fastapi import APIRouter

from app.modules.auth.presentation.router import router as auth_router

api_router = APIRouter()
api_router.include_router(auth_router)
