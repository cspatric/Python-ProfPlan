# 0003 — Draft plans in a worker, not in the request

**Status:** Accepted · 2026-08-14 · supersedes the original synchronous design

## Context

`POST /plans` used to call the planner inside the request. The AI takes up to a
minute, so the request held a connection open for up to a minute.

The original design was deliberate and its reasoning was good: the planner ran
**before anything was persisted**, so if the AI failed the request failed and
no plan was created. There was never a plan without a roadmap.

The failure mode was worse than the guarantee. A browser that lost the
connection during that minute left the teacher looking at nothing, while the
plan existed in the database with no way back to it. That happened during
development, on a local machine, on a normal connection.

## Decision

Create the plan, open a generation run as `PLANNING`, queue the drafting, and
answer immediately with the run to watch.

Measured on a real generation: **50 ms to answer**, against the minute it used
to hold. The roadmap arrived 20 seconds later and the page filled itself in
without a reload.

## Consequences

- **A plan can now exist before its roadmap does.** This is the guarantee that
  was traded away, and it was traded knowingly.
- A planner failure lands on the run as `FAILED` with the reason, instead of
  failing a request nobody may still be waiting on. That state is visible on
  the plan page; a dropped request is not.
- The page has to say which of three things is true: drafting, drafted, or
  never arrived. It polls, bounded, and says so.
- The composition the teacher chose (how many exams, which kinds) is recorded
  **on the run**, because it is not a column of the plan. Moving the planner
  off the request thread would otherwise have dropped it in silence, which is
  the kind of bug this whole record is trying to make visible.

## What would change this

- **If a plan without a roadmap turns out to be worse than a plan nobody can
  see.** The old guarantee is recoverable: create the plan only when the
  drafting succeeds, and let the client poll a run that has no plan yet. That
  is more machinery for a case that may not matter.
- **If the planner gets fast.** Under a second or two, the whole trade
  disappears and the synchronous version is simpler.
