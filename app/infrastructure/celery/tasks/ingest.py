"""Celery task that runs the document ingestion pipeline asynchronously.

Transient failures (e.g. the embedding model being briefly unavailable) are
retried with exponential backoff. Once retries are exhausted the document is
marked FAILED, with the error stored on it for visibility via the status API.
"""

import asyncio
from uuid import UUID

from app.infrastructure.celery.worker import celery_app
from app.infrastructure.database.session import WorkerSessionFactory
from app.infrastructure.storage.minio import get_object_storage
from app.modules.documents.domain.entities import IngestionStatus
from app.modules.documents.infrastructure.repository import (
    DocumentContentRepository,
    DocumentRepository,
)
from app.modules.rag.application.indexing_service import IndexingService
from app.modules.rag.application.ingestion_service import IngestionService
from app.modules.rag.infrastructure.embedding.cache import build_cached_embedder
from app.modules.rag.infrastructure.repository import ChunkRepository
from app.shared.exceptions.base import AppError

_MAX_RETRIES = 3


async def _run(document_id: UUID) -> None:
    async with WorkerSessionFactory() as session:
        indexing = IndexingService(
            session, ChunkRepository(session), DocumentContentRepository(session)
        )
        service = IngestionService(
            session,
            storage=get_object_storage(),
            embedder=build_cached_embedder(),
            documents=DocumentRepository(session),
            contents=DocumentContentRepository(session),
            indexing=indexing,
        )
        await service.ingest(document_id)


async def _mark_failed(document_id: UUID, error: str) -> None:
    async with WorkerSessionFactory() as session:
        await DocumentRepository(session).set_ingestion_status(
            document_id, IngestionStatus.FAILED, error=error[:2000]
        )
        await session.commit()


@celery_app.task(bind=True, name="documents.ingest", max_retries=_MAX_RETRIES)
def ingest_document(self, document_id: str) -> None:
    """Entry point enqueued after a document upload."""
    doc_uuid = UUID(document_id)
    try:
        asyncio.run(_run(doc_uuid))
    except AppError as exc:
        # Permanent errors (e.g. unsupported/corrupt file): fail fast, no retry.
        asyncio.run(_mark_failed(doc_uuid, str(exc)))
        raise
    except Exception as exc:
        # Transient errors (e.g. embedding model briefly down): retry, then fail.
        if self.request.retries >= self.max_retries:
            asyncio.run(_mark_failed(doc_uuid, str(exc)))
            raise
        # Exponential backoff: 15s, 30s, 60s.
        raise self.retry(exc=exc, countdown=15 * 2**self.request.retries) from exc
