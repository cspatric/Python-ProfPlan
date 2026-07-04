"""Indexing use case: persist a document content's chunks (with embeddings)."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
)
from app.modules.rag.domain.chunk import ChunkInput
from app.modules.rag.domain.exceptions import InvalidContentError
from app.modules.rag.infrastructure.models import Chunk
from app.modules.rag.infrastructure.repository import ChunkRepository


class IndexingService:
    """Stores the chunks of a parsed document content for retrieval."""

    def __init__(
        self,
        session: AsyncSession,
        chunks: ChunkRepository,
        contents: DocumentContentRepository,
    ) -> None:
        self._session = session
        self._chunks = chunks
        self._contents = contents

    async def index_content(
        self,
        *,
        content_id: UUID,
        chunks: Sequence[ChunkInput],
        replace: bool = True,
    ) -> list[Chunk]:
        """Index the given chunks under a document content.

        When ``replace`` is True, existing chunks of the content are removed
        first (idempotent re-indexing).
        """
        if await self._contents.get_by_id(content_id) is None:
            raise InvalidContentError

        if replace:
            await self._chunks.delete_by_content(content_id)

        rows = [
            Chunk(
                document_content_id=content_id,
                chunk_index=item.chunk_index,
                content=item.content,
                token_count=item.token_count,
                embedding=item.embedding,
            )
            for item in chunks
        ]
        self._chunks.add_many(rows)
        await self._session.commit()
        return rows
