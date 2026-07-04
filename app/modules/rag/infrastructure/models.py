"""SQLAlchemy model for document chunks with embeddings (RAG)."""

from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import EMBEDDING_DIMENSIONS
from app.infrastructure.database.base import Base


class Chunk(Base):
    """A slice of a parsed document content, with its embedding vector.

    Chunks belong to a `document_content` (a specific parsed version), so the
    parsing metadata (language, parser, version) is NOT duplicated here — it
    lives on `document_content`.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_content_id", "chunk_index"),
        # Approximate nearest-neighbour index for cosine similarity search.
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    document_content_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document_content.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
