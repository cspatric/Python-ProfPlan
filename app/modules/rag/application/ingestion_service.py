"""Ingestion pipeline: file -> markdown -> chunks -> embeddings -> index."""

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.storage.minio import ObjectStorage
from app.modules.documents.domain.entities import IngestionStatus
from app.modules.documents.infrastructure.models import DocumentContent
from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
    DocumentRepository,
)
from app.modules.rag.application.indexing_service import IndexingService
from app.modules.rag.domain.chunk import ChunkInput
from app.modules.rag.domain.interfaces import Embedder
from app.modules.rag.infrastructure.chunking.chunker import chunk_markdown
from app.modules.rag.infrastructure.parser.document_parser import (
    parse_to_markdown,
)


class IngestionService:
    """Turns an uploaded document into indexed, embedded chunks."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        storage: ObjectStorage,
        embedder: Embedder,
        documents: DocumentRepository,
        contents: DocumentContentRepository,
        indexing: IndexingService,
    ) -> None:
        self._session = session
        self._storage = storage
        self._embedder = embedder
        self._documents = documents
        self._contents = contents
        self._indexing = indexing

    async def ingest(self, document_id: UUID) -> DocumentContent | None:
        """Run the full ingestion pipeline for a stored document.

        The status only flips to INDEXED once the chunks (with embeddings) are
        actually persisted in pgvector — never before.

        Idempotent: a redelivered Celery task or a duplicate trigger for a
        document that's already PROCESSING or INDEXED is a safe no-op instead
        of re-downloading, re-parsing and re-embedding from scratch.
        """
        document = await self._documents.get_for_processing(document_id)
        if document is None:
            return None
        if document.ingestion_status in (
            IngestionStatus.PROCESSING,
            IngestionStatus.INDEXED,
        ):
            return None

        await self._documents.set_ingestion_status(
            document_id, IngestionStatus.PROCESSING, error=None
        )
        await self._session.commit()

        data = await asyncio.to_thread(self._storage.get_object, document.document_path)
        markdown = parse_to_markdown(document.document_path, data)

        latest = await self._contents.get_latest(document_id)
        version = latest.version + 1 if latest else 1
        content = DocumentContent(
            document_id=document_id,
            markdown=markdown,
            parser="auto",
            version=version,
        )
        self._contents.add(content)
        await self._session.commit()
        await self._session.refresh(content)

        pieces = chunk_markdown(markdown)
        if pieces:
            embeddings = await self._embedder.embed_texts(pieces)
            chunks = [
                ChunkInput(
                    chunk_index=index,
                    content=piece,
                    token_count=len(piece.split()),
                    embedding=embedding,
                )
                for index, (piece, embedding) in enumerate(
                    zip(pieces, embeddings, strict=True)
                )
            ]
            await self._indexing.index_content(content_id=content.uuid, chunks=chunks)

        # Chunks are now in pgvector (or the document was legitimately empty):
        # only now is the document truly searchable.
        await self._documents.set_ingestion_status(document_id, IngestionStatus.INDEXED)
        await self._session.commit()
        return content
