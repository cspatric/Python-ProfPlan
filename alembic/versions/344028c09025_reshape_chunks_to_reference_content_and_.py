"""reshape chunks to reference content and add embedding

Revision ID: 344028c09025
Revises: 23b9bd6af1f0
Create Date: 2026-07-04 22:43:37.468371

"""
from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "344028c09025"
down_revision: str | None = "23b9bd6af1f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSIONS = 768


def upgrade() -> None:
    # Chunks now belong to a document_content (not the document directly) and
    # carry chunk-specific data only; parsing metadata stays on document_content.
    op.drop_table("chunks")
    op.create_table(
        "chunks",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "document_content_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_content_id"],
            ["document_content.uuid"],
            name=op.f("fk_chunks_document_content_id_document_content"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uuid", name=op.f("pk_chunks")),
        sa.UniqueConstraint(
            "document_content_id",
            "chunk_index",
            name=op.f("uq_chunks_document_content_id"),
        ),
    )
    op.create_index(
        op.f("ix_chunks_document_content_id"),
        "chunks",
        ["document_content_id"],
        unique=False,
    )
    op.create_index(
        "ix_chunks_embedding",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_embedding", table_name="chunks")
    op.drop_index(op.f("ix_chunks_document_content_id"), table_name="chunks")
    op.drop_table("chunks")
    op.create_table(
        "chunks",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("parser", sa.String(length=128), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.uuid"],
            name=op.f("fk_chunks_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uuid", name=op.f("pk_chunks")),
    )
    op.create_index(
        op.f("ix_chunks_document_id"), "chunks", ["document_id"], unique=False
    )
