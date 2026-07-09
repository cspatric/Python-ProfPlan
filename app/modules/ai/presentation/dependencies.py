"""FastAPI dependencies for the AI module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.database.session import SessionFactory, get_session
from app.modules.ai.application.providers_service import AiProvidersService
from app.modules.ai.application.service import AiService
from app.modules.ai.infrastructure.gateway.llm_gateway import get_gateway
from app.modules.ai.infrastructure.repository import AiProviderRepository
from app.modules.audit.presentation.dependencies import AuditRecorderDep
from app.modules.rag.infrastructure.embedding.cache import build_cached_embedder


def get_ai_service() -> AiService:
    """Build an AiService.

    Deliberately does NOT take a request-scoped session (unlike every other
    service in this codebase) — it opens/closes its own short-lived one
    internally, before the LLM call, so the DB pool isn't held during an
    outbound request that can take several minutes. See AiService's docstring.
    """
    return AiService(get_gateway(), SessionFactory, build_cached_embedder())


AiServiceDep = Annotated[AiService, Depends(get_ai_service)]


def get_ai_providers_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    audit: AuditRecorderDep,
) -> AiProvidersService:
    """Build the AiProvidersService (gateway + ai_provider table + audit)."""
    return AiProvidersService(
        session,
        get_gateway(),
        AiProviderRepository(session),
        get_settings(),
        audit,
    )


AiProvidersServiceDep = Annotated[AiProvidersService, Depends(get_ai_providers_service)]
