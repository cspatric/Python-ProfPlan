"""FastAPI dependencies for the RAG module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
)
from app.modules.rag.application.retrieval_service import RetrievalService
from app.modules.rag.application.search_service import SearchService
from app.modules.rag.infrastructure.embedding.ollama_embedding import (
    OllamaEmbedding,
)
from app.modules.rag.infrastructure.repository import ChunkRepository


def get_retrieval_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RetrievalService:
    """Build a RetrievalService wired to the request-scoped session."""
    return RetrievalService(
        OllamaEmbedding(),
        SearchService(ChunkRepository(session)),
        DocumentContentRepository(session),
    )


RetrievalServiceDep = Annotated[RetrievalService, Depends(get_retrieval_service)]
