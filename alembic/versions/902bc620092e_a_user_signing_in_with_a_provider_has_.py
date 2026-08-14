"""a user signing in with a provider has no password

Sign in with Google creates accounts that genuinely have no password. Storing a
random placeholder hash instead would make "does this account have a password"
a question nothing can answer, and would let a password reset silently appear
to work on an account that never had one.

Widening a NOT NULL to nullable needs no data migration: every existing row
already has a value and keeps it.

Note for whoever regenerates a migration here: autogenerate always proposes
dropping ``uq_users_email_active`` and creating a plain ``ix_users_email``. It
is wrong. That index is partial (``WHERE deleted_at IS NULL``) so a
soft-deleted account frees its address; a plain unique index would forbid ever
reusing it. The proposal was removed by hand, as in every migration before this.

Revision ID: 902bc620092e
Revises: f239d2b700ba
Create Date: 2026-08-14 14:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "902bc620092e"
down_revision: str | None = "f239d2b700ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    # Anyone who only ever signed in with Google has no password to put back,
    # so narrowing this again would fail on their row. Those accounts have to
    # be dealt with before a downgrade, not silently given a fake hash.
    op.execute("DELETE FROM user_providers WHERE user_id IN "
               "(SELECT uuid FROM users WHERE password_hash IS NULL)")
    op.execute("DELETE FROM users WHERE password_hash IS NULL")
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=False,
    )
