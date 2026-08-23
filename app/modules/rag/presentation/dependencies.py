"""FastAPI dependencies for the RAG module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_read_session
from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
)
from app.modules.rag.application.retrieval_service import RetrievalService
from app.modules.rag.application.search_service import SearchService
from app.modules.rag.infrastructure.embedding.cache import build_cached_embedder
from app.modules.rag.infrastructure.repository import ChunkRepository


def get_retrieval_service(
    session: Annotated[AsyncSession, Depends(get_read_session)],
) -> RetrievalService:
    """Build a RetrievalService wired to a read session.

    Retrieval is pure search: it embeds a query and reads chunks written by an
    ingestion that finished earlier, in another request, so there is no
    read-after-write relationship with the caller's own traffic. That makes it
    the safest and heaviest read to move off the primary — and it is the one
    that grows with the corpus rather than with the number of users.

    Vector search is also the query that scales worst on shared hardware, so
    keeping it on the same machine as the write path is what would starve
    writes first.
    """
    return RetrievalService(
        build_cached_embedder(),
        SearchService(ChunkRepository(session)),
        DocumentContentRepository(session),
    )


RetrievalServiceDep = Annotated[RetrievalService, Depends(get_retrieval_service)]
