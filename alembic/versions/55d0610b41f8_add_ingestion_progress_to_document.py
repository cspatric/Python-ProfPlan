"""add ingestion progress to document

Ingesting a long document is minutes of embedding on a CPU. These three
columns are what let the app say how far along it is and how much longer it
will take, instead of showing an indefinite spinner: the total is written once
the text is chunked, the count climbs as each batch is embedded, and the start
time is what the estimate is computed against (the rate this machine is
actually managing, not a constant).

Note for whoever regenerates a migration here: autogenerate always proposes
dropping ``uq_users_email_active`` and creating a plain ``ix_users_email``. It
is wrong. That index is a partial unique index (``WHERE deleted_at IS NULL``)
which lets a soft-deleted account free its email; a plain unique index would
forbid ever reusing it. The proposal was removed by hand, as in the two
migrations before this one.

Revision ID: 55d0610b41f8
Revises: e10e0a2be1e9
Create Date: 2026-08-13 20:47:25.071277

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "55d0610b41f8"
down_revision: str | None = "e10e0a2be1e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document", sa.Column("ingestion_chunks_total", sa.Integer(), nullable=True)
    )
    op.add_column(
        "document", sa.Column("ingestion_chunks_done", sa.Integer(), nullable=True)
    )
    op.add_column(
        "document",
        sa.Column("ingestion_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document", "ingestion_started_at")
    op.drop_column("document", "ingestion_chunks_done")
    op.drop_column("document", "ingestion_chunks_total")
