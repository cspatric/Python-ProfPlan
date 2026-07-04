"""Celery task that runs the document ingestion pipeline asynchronously."""

import asyncio
from uuid import UUID

from app.infrastructure.celery.worker import celery_app
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.storage.minio import get_object_storage
from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
    DocumentRepository,
)
from app.modules.rag.application.indexing_service import IndexingService
from app.modules.rag.application.ingestion_service import IngestionService
from app.modules.rag.infrastructure.embedding.ollama_embedding import (
    OllamaEmbedding,
)
from app.modules.rag.infrastructure.repository import ChunkRepository


async def _run(document_id: UUID) -> None:
    async with SessionFactory() as session:
        indexing = IndexingService(
            session, ChunkRepository(session), DocumentContentRepository(session)
        )
        service = IngestionService(
            session,
            storage=get_object_storage(),
            embedder=OllamaEmbedding(),
            documents=DocumentRepository(session),
            contents=DocumentContentRepository(session),
            indexing=indexing,
        )
        await service.ingest(document_id)


@celery_app.task(name="documents.ingest")
def ingest_document(document_id: str) -> None:
    """Entry point enqueued after a document upload."""
    asyncio.run(_run(UUID(document_id)))
