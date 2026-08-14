"""keep the original filename of an upload

The stored path is a uuid, so once a file was uploaded the only thing naming it
was a title that defaults to the file name. A file named with a hash left
nothing to recognise the document by, which is how reference material can end
up attached to a subject without anyone being able to tell what it is.

Nullable, and left null for everything uploaded before this: the name was never
recorded and cannot be recovered.

Note for whoever regenerates a migration here: autogenerate always proposes
dropping ``uq_users_email_active`` and creating a plain ``ix_users_email``. It
is wrong. That index is partial (``WHERE deleted_at IS NULL``) so a
soft-deleted account frees its email; a plain unique index would forbid ever
reusing it. The proposal was removed by hand, as in the migrations before this.

Revision ID: f239d2b700ba
Revises: 55d0610b41f8
Create Date: 2026-08-14 03:41:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f239d2b700ba"
down_revision: str | None = "55d0610b41f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document", sa.Column("original_filename", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("document", "original_filename")
