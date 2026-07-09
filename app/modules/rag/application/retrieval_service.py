"""Retrieval use case: embed a question and search the user's chunks."""

from uuid import UUID

from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
)
from app.modules.rag.application.search_service import SearchService
from app.modules.rag.domain.chunk import SearchResult
from app.modules.rag.domain.interfaces import Embedder


class RetrievalService:
    """Answers a RAG query with the most relevant chunks the user can read."""

    def __init__(
        self,
        embedder: Embedder,
        search: SearchService,
        contents: DocumentContentRepository,
    ) -> None:
        self._embedder = embedder
        self._search = search
        self._contents = contents

    async def query(
        self,
        *,
        user_id: UUID,
        query: str,
        subject_id: UUID | None = None,
        content_ids: list[UUID] | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Embed the query and return the closest chunks owned by the user.

        ``content_ids`` restricts the search to specific parsed contents (e.g.
        the documents a plan selected); when omitted it falls back to all of the
        user's documents, optionally scoped to ``subject_id``.
        """
        if content_ids is None:
            content_ids = await self._contents.list_content_ids_for_user(
                user_id, subject_id
            )
        if not content_ids:
            return []
        embedding = await self._embedder.embed_text(query)
        return await self._search.search(
            query_embedding=embedding, limit=limit, content_ids=content_ids
        )
