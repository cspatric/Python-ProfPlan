# 0004 — Soft delete, cascading by hand

**Status:** Accepted

## Context

A teacher deletes a subject. Underneath it are plans, modules, activities and
uploaded documents, and the foreign keys are set to cascade on delete.

Two questions had to be answered together. Does deleting mean the rows leave,
and if the rows stay, what happens to everything hanging off them?

## Decision

Rows are marked `deleted_at` rather than removed, and the cascade is performed
in application code (`cascade_soft_delete`) rather than by the database.

Every read filters on `deleted_at IS NULL`, so a soft-deleted row is invisible
to the app while remaining in the table.

## Consequences

- A deletion is recoverable by hand. For a teacher who has just lost a term of
  planning to a mis-click, that is the difference between an apology and a
  `UPDATE`.
- The audit trail keeps pointing at rows that still exist. A hard delete leaves
  audit entries about rows nobody can look at.
- **The cascade is code, not a constraint, so it can be forgotten.** Adding a
  table that hangs off subjects without adding it to `cascade_soft_delete`
  leaves orphans that are live rows the app still reads. There is an
  integration test covering the existing chain, and it is the only thing
  standing between this design and that bug.
- Uniqueness has to account for it. `users.email` uses a **partial** unique
  index (`WHERE deleted_at IS NULL`) so a deleted account frees its address.
  Alembic's autogenerate proposes replacing it with a plain unique index on
  every run, which would forbid ever reusing an email; that proposal is
  removed by hand in every migration and the reason is written in each one.
- Nothing purges. Deleted rows accumulate forever, and the storage they hold is
  never reclaimed.

## What would change this

- **A retention obligation.** If the product ever has to promise that deleted
  material is gone, this design is the opposite of that, and a purge job with a
  grace period becomes mandatory rather than optional.
- **Volume.** Nothing prunes today; if deleted rows ever outweigh live ones the
  filtered reads start paying for them.
