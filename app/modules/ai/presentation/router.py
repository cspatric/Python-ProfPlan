"""AI HTTP endpoints."""

from fastapi import APIRouter

from app.modules.ai.presentation.dependencies import AiServiceDep
from app.modules.ai.presentation.schemas import AiAnswerResponse, AiAskRequest
from app.modules.auth.presentation.dependencies import CurrentUser

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
