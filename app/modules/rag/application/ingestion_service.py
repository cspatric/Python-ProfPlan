"""Ingestion pipeline: file -> markdown -> chunks -> embeddings -> index."""

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.storage.minio import ObjectStorage
from app.modules.documents.infrastructure.models import DocumentContent
from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
    DocumentRepository,
)
from app.modules.rag.application.indexing_service import IndexingService
from app.modules.rag.domain.chunk import ChunkInput
from app.modules.rag.infrastructure.chunking.chunker import chunk_markdown
from app.modules.rag.infrastructure.embedding.ollama_embedding import (
    OllamaEmbedding,
)
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
        embedder: OllamaEmbedding,
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
        """Run the full ingestion pipeline for a stored document."""
        document = await self._documents.get_for_processing(document_id)
        if document is None:
            return None

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
        if not pieces:
            return content

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
        return content
