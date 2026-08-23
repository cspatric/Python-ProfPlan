"""english item kinds

The kinds of academic item (`content`, `exam`, `assignment`, ...) used to be
stored in Portuguese, because that is what the planner emitted. Everything in
this codebase is English, so the values are now too — and this rewrites the rows
that already hold the old ones.

Two places store them, and both are JSONB rather than a column, which is why
this is data and not a type change:

* `academic_items.metadata->>'kind'` — one value per generated item.
* `plan_generation.input->'kinds'` and `->'counts'` — what the teacher asked
  for, read back when a run is resumed.

Reading is tolerant either way (`normalize_kind` keeps the Portuguese words as
aliases, which is where words a model writes belong), so a row this misses still
renders correctly. The migration exists so queries and exports see one
vocabulary rather than two.

Revision ID: b8f2d4c6a071
Revises: a3c8e5b7d129
Create Date: 2026-08-23 15:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8f2d4c6a071"
down_revision: str | None = "a3c8e5b7d129"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: old -> new. "quiz" is spelled the same in both and is deliberately absent.
_RENAMES = {
    "conteudo": "content",
    "leitura": "reading",
    "exercicios": "exercises",
    "atividade": "activity",
    "laboratorio": "lab",
    "projeto": "project",
    "seminario": "seminar",
    "trabalho": "assignment",
    "prova": "exam",
    "bibliografia": "bibliography",
}


def _rewrite(mapping: dict[str, str]) -> None:
    for old, new in mapping.items():
        # One value per item, in the metadata object.
        op.execute(
            "UPDATE academic_items "
            f"SET metadata = jsonb_set(metadata, '{{kind}}', '\"{new}\"') "
            f"WHERE metadata->>'kind' = '{old}'"
        )
        # The list of kinds the teacher ticked.
        op.execute(
            "UPDATE plan_generation "
            "SET input = jsonb_set("
            "  input, '{kinds}',"
            f"  (SELECT jsonb_agg(CASE WHEN value::text = '\"{old}\"' "
            f"          THEN '\"{new}\"'::jsonb ELSE value END)"
            "   FROM jsonb_array_elements(input->'kinds') AS value)"
            ") "
            f"WHERE input->'kinds' @> '[\"{old}\"]'"
        )
        # The per-kind counts, whose keys are the kinds themselves.
        op.execute(
            "UPDATE plan_generation "
            "SET input = jsonb_set("
            "  input, '{counts}',"
            f"  (input->'counts') - '{old}' || "
            f"  jsonb_build_object('{new}', input->'counts'->'{old}')"
            ") "
            f"WHERE input->'counts' ? '{old}'"
        )


def upgrade() -> None:
    _rewrite(_RENAMES)


def downgrade() -> None:
    _rewrite({new: old for old, new in _RENAMES.items()})
