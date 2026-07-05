"""FastAPI dependencies for the AI module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.ai.application.service import AiService
from app.modules.ai.infrastructure.gateway.llm_gateway import get_gateway
from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
)
from app.modules.rag.application.retrieval_service import RetrievalService
from app.modules.rag.application.search_service import SearchService
from app.modules.rag.infrastructure.embedding.cache import build_cached_embedder
from app.modules.rag.infrastructure.repository import ChunkRepository


def get_ai_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AiService:
    """Build an AiService (RAG retrieval + LLM gateway)."""
    retrieval = RetrievalService(
        build_cached_embedder(),
        SearchService(ChunkRepository(session)),
        DocumentContentRepository(session),
    )
    return AiService(get_gateway(), retrieval)


AiServiceDep = Annotated[AiService, Depends(get_ai_service)]
