"""Ingestion pipeline: file -> markdown -> chunks -> embeddings -> index."""

import asyncio
from datetime import UTC, datetime, timedelta
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

#: How long a document may sit in PROCESSING before another run may take it
#: over. Long enough that a slow but living ingestion is never interrupted (a
#: hundred-chunk document on a CPU-only embedder takes minutes), short enough
#: that a run killed by a reboot does not strand the document for a day.
_STALE_AFTER = timedelta(minutes=30)


def _is_stale(updated_at: datetime | None) -> bool:
    if updated_at is None:
        return True
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - updated_at > _STALE_AFTER


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
        document that's already INDEXED, or that another worker is actively
        processing, is a safe no-op instead of re-downloading, re-parsing and
        re-embedding from scratch.

        "Actively" is the important word. A document left PROCESSING by a run
        that died (a timeout, a killed worker, a reboot) is not being worked on
        by anyone, and treating it as if it were is what made a failed
        ingestion permanent: the Celery retry returned here immediately,
        reported success, and the document sat spinning in the UI forever. Past
        the stale threshold it is taken over.
        """
        document = await self._documents.get_for_processing(document_id)
        if document is None:
            return None
        if document.ingestion_status is IngestionStatus.INDEXED:
            return None
        if document.ingestion_status is IngestionStatus.PROCESSING and not _is_stale(
            document.updated_at
        ):
            return None

        try:
            return await self._ingest(document_id, document.document_path)
        except Exception as exc:
            # Leave a document that failed in FAILED, not in PROCESSING. It is
            # what tells the retry it may take the work, and what lets the page
            # say something happened instead of spinning.
            await self._session.rollback()
            await self._documents.set_ingestion_status(
                document_id, IngestionStatus.FAILED, error=str(exc)[:2000]
            )
            await self._session.commit()
            raise

    async def _ingest(
        self, document_id: UUID, document_path: str
    ) -> DocumentContent | None:
        await self._documents.set_ingestion_status(
            document_id, IngestionStatus.PROCESSING, error=None
        )
        await self._session.commit()

        data = await asyncio.to_thread(self._storage.get_object, document_path)
        markdown = parse_to_markdown(document_path, data)

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
            # The total is only knowable here, after parsing and chunking.
            # Publishing it now, and the count as each batch lands, is what
            # lets the page show progress and an estimate instead of an
            # indefinite spinner on a job that runs for minutes.
            await self._documents.set_ingestion_progress(
                document_id, done=0, total=len(pieces)
            )
            await self._session.commit()

            async def report(done: int) -> None:
                await self._documents.set_ingestion_progress(
                    document_id, done=done, total=len(pieces)
                )
                await self._session.commit()

            embeddings = await self._embedder.embed_texts(pieces, on_progress=report)
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
