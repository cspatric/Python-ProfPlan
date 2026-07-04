"""RAG retrieval HTTP endpoints."""

from fastapi import APIRouter

from app.modules.auth.presentation.dependencies import CurrentUser
from app.modules.rag.presentation.dependencies import RetrievalServiceDep
from app.modules.rag.presentation.schemas import (
    RagChunkResult,
    RagQueryRequest,
    RagQueryResponse,
)

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/query", response_model=RagQueryResponse)
async def query_rag(
    payload: RagQueryRequest,
    user: CurrentUser,
    service: RetrievalServiceDep,
) -> RagQueryResponse:
    """Embed the query and return the most relevant chunks the user can read."""
    results = await service.query(
        user_id=user.uuid,
        query=payload.query,
        subject_id=payload.subject_id,
        limit=payload.limit,
    )
    return RagQueryResponse(
        query=payload.query,
        results=[
            RagChunkResult(
                chunk_id=result.chunk_id,
                document_content_id=result.document_content_id,
                content=result.content,
                distance=result.distance,
                score=round(1.0 - result.distance, 6),
            )
            for result in results
        ],
    )
