"""search chunks by words as well as by meaning

A vector search is very good at "what is this about" and reliably bad at
tokens that carry no meaning to average: a surname, an acronym, a formula, a
year, a product code. "van Helmont" and "RuBisCO" embed as noise near other
noise. Lexical search is the opposite, and putting them together is the whole
point.

The column is GENERATED, so nothing in the application can forget to fill it:
a chunk that exists is a chunk that is searchable, including every chunk that
was indexed before this migration ran.

``english`` as the configuration, and the only thing that actually matters is
that the **query uses the same one**: stemming is a mapping, and a mapping
applied to both sides matches itself whatever language the text is in. What
`english` adds over `simple` is stopword removal, which a lexical search needs
far more than it needs correct stemming: with `simple`, "how", "do" and "the"
are indexed terms, and a question made mostly of them ranks every chunk in the
corpus equally. Names, acronyms and numbers, the tokens this half exists to
catch, pass through any stemmer unchanged.

Revision ID: a41c9e2b77d5
Revises: 917537b373e4
Create Date: 2026-08-14 23:40:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a41c9e2b77d5"
down_revision: str | None = "917537b373e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chunks ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
    )
    # GIN, not GiST: this index is read far more than it is written (a chunk is
    # written once and read on every search) and GIN answers faster.
    op.execute("CREATE INDEX ix_chunks_content_tsv ON chunks USING gin (content_tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_tsv")
