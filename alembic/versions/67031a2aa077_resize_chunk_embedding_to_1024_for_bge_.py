"""resize chunk embedding to 1024 for bge-m3

Revision ID: 67031a2aa077
Revises: 344028c09025
Create Date: 2026-07-04 22:56:42.562123

"""
from collections.abc import Sequence

from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "67031a2aa077"
down_revision: str | None = "344028c09025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _resize(new_dim: int, old_dim: int) -> None:
    # The vector index must be dropped before altering the column type.
    op.drop_index("ix_chunks_embedding", table_name="chunks")
    op.alter_column(
        "chunks",
        "embedding",
        existing_type=Vector(old_dim),
        type_=Vector(new_dim),
        existing_nullable=True,
    )
    op.create_index(
        "ix_chunks_embedding",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def upgrade() -> None:
    _resize(new_dim=1024, old_dim=768)


def downgrade() -> None:
    _resize(new_dim=768, old_dim=1024)
