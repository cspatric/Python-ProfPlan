"""add ingestion status to document

Revision ID: e5a1b2c3d4f0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-05 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e5a1b2c3d4f0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    ingestion_status = postgresql.ENUM(
        "PENDING", "PROCESSING", "INDEXED", "FAILED", name="ingestion_status"
    )
    ingestion_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "document",
        sa.Column(
            "ingestion_status",
            postgresql.ENUM(
                "PENDING",
                "PROCESSING",
                "INDEXED",
                "FAILED",
                name="ingestion_status",
                create_type=False,
            ),
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.add_column("document", sa.Column("ingestion_error", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_document_ingestion_status"),
        "document",
        ["ingestion_status"],
        unique=False,
    )

    # Backfill: documents that already have parsed content are considered indexed.
    op.execute(
        "UPDATE document SET ingestion_status = 'INDEXED' "
        "WHERE uuid IN (SELECT DISTINCT document_id FROM document_content)"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_ingestion_status"), table_name="document")
    op.drop_column("document", "ingestion_error")
    op.drop_column("document", "ingestion_status")
    postgresql.ENUM(name="ingestion_status").drop(op.get_bind(), checkfirst=True)
