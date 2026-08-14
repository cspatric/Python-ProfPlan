"""Unit tests for what happens when an ingestion fails.

These pin the behaviour that was missing when a large document could not be
embedded: the run died, the document stayed PROCESSING, and every Celery retry
returned immediately reporting success. The document spun in the UI forever and
the error was never recorded anywhere.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.modules.documents.domain.entities import IngestionStatus
from app.modules.rag.application.ingestion_service import IngestionService


class FakeSession:
    def __init__(self) -> None:
        self.rolled_back = False

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, _obj) -> None:
        pass


class FakeDocuments:
    """A single document, whose status this test watches."""

    def __init__(self, status: IngestionStatus, updated_at: datetime) -> None:
        self.document = SimpleNamespace(
            ingestion_status=status,
            updated_at=updated_at,
            document_path="uploads/notes.txt",
        )
        self.history: list[tuple[IngestionStatus, str | None]] = []

    async def get_for_processing(self, _document_id: UUID):
        return self.document

    async def set_ingestion_status(
        self, _document_id: UUID, status: IngestionStatus, error: str | None = None
    ) -> None:
        self.document.ingestion_status = status
        self.history.append((status, error))


class ExplodingStorage:
    """Stands in for the step that failed in production (the embedder)."""

    def get_object(self, _path: str) -> bytes:
        raise TimeoutError("the embedder took too long")


def build(
    status: IngestionStatus, age: timedelta
) -> tuple[IngestionService, FakeDocuments]:
    documents = FakeDocuments(status, datetime.now(UTC) - age)
    service = IngestionService(
        FakeSession(),
        storage=ExplodingStorage(),
        embedder=object(),
        documents=documents,
        contents=object(),
        indexing=object(),
    )
    return service, documents


async def test_a_failure_leaves_the_document_failed_not_processing() -> None:
    service, documents = build(IngestionStatus.PENDING, timedelta(0))

    with pytest.raises(TimeoutError):
        await service.ingest(uuid4())

    assert documents.document.ingestion_status is IngestionStatus.FAILED
    # And the reason is kept, so the page can say what went wrong.
    assert documents.history[-1][1] == "the embedder took too long"


async def test_an_indexed_document_is_left_alone() -> None:
    service, documents = build(IngestionStatus.INDEXED, timedelta(0))

    assert await service.ingest(uuid4()) is None
    assert documents.history == []


async def test_a_document_another_worker_is_on_is_left_alone() -> None:
    # Still fresh: someone is genuinely working on it, and a hundred-chunk
    # document legitimately takes minutes.
    service, documents = build(IngestionStatus.PROCESSING, timedelta(minutes=5))

    assert await service.ingest(uuid4()) is None
    assert documents.history == []


async def test_a_stranded_document_is_taken_over() -> None:
    # Nobody is on this one: the run that claimed it died (a killed worker, a
    # reboot). Skipping it here is what made the state permanent.
    service, documents = build(IngestionStatus.PROCESSING, timedelta(hours=2))

    with pytest.raises(TimeoutError):
        await service.ingest(uuid4())

    assert documents.document.ingestion_status is IngestionStatus.FAILED


async def test_a_failed_document_is_retried() -> None:
    service, documents = build(IngestionStatus.FAILED, timedelta(minutes=1))

    with pytest.raises(TimeoutError):
        await service.ingest(uuid4())

    assert documents.history[0][0] is IngestionStatus.PROCESSING


class EmptyStorage:
    """A file that parses to nothing, the scanned-PDF case."""

    def get_object(self, _path: str) -> bytes:
        return b""


class FakeContents:
    """Just enough of the content repository to reach the chunking step."""

    def add(self, _content) -> None:
        pass

    async def get_latest(self, _document_id: UUID):
        return None


async def test_a_file_with_no_readable_text_is_not_reported_as_indexed() -> None:
    """The worst outcome available is silence.

    The file was accepted, stored and parsed, and produced nothing to search.
    Marking it INDEXED tells the teacher it is feeding the AI when it is
    feeding it nothing, and there is no way to find that out from the app.
    """
    documents = FakeDocuments(IngestionStatus.PENDING, datetime.now(UTC))
    service = IngestionService(
        FakeSession(),
        storage=EmptyStorage(),
        embedder=object(),
        documents=documents,
        contents=FakeContents(),
        indexing=object(),
    )

    with pytest.raises(Exception) as raised:
        await service.ingest(uuid4())

    assert documents.document.ingestion_status is IngestionStatus.FAILED
    assert "no text layer" in documents.history[-1][1]
    assert "readable text" in str(raised.value)
