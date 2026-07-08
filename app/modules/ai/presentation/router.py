"""AI HTTP endpoints."""

from fastapi import APIRouter

from app.modules.ai.presentation.dependencies import (
    AiProvidersServiceDep,
    AiServiceDep,
)
from app.modules.ai.presentation.schemas import (
    AiAnswerResponse,
    AiAskRequest,
    AiHealthResponse,
    ProviderStatusResponse,
    ProviderToggleRequest,
)
from app.modules.auth.presentation.dependencies import CurrentAdmin, CurrentUser

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/ask", response_model=AiAnswerResponse)
async def ask(
    payload: AiAskRequest, user: CurrentUser, service: AiServiceDep
) -> AiAnswerResponse:
    """Answer a question grounded on the user's documents (RAG + LLM gateway)."""
    result = await service.answer(
        user_id=user.uuid,
        query=payload.query,
        subject_id=payload.subject_id,
        limit=payload.limit,
    )
    return AiAnswerResponse(
        answer=result.answer,
        provider=result.provider,
        sources=result.sources,
    )


@router.get("/health", response_model=AiHealthResponse)
async def ai_health(
    _user: CurrentUser, service: AiProvidersServiceDep
) -> AiHealthResponse:
    """List the LLM providers (fallback order) and their runtime status."""
    statuses = await service.list_all()
    return AiHealthResponse(
        providers=[ProviderStatusResponse.model_validate(s) for s in statuses]
    )


@router.patch("/providers/{name}", response_model=AiHealthResponse)
async def toggle_provider(
    name: str,
    payload: ProviderToggleRequest,
    _admin: CurrentAdmin,
    service: AiProvidersServiceDep,
) -> AiHealthResponse:
    """Enable/disable a provider (admin).

    Ollama can't be disabled and at least one provider besides Ollama must stay
    active — violations return 409.
    """
    statuses = await service.set_enabled(name, payload.enabled)
    return AiHealthResponse(
        providers=[ProviderStatusResponse.model_validate(s) for s in statuses]
    )
