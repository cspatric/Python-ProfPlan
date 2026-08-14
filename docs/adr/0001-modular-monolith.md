# 0001 — A modular monolith, layered per module

**Status:** Accepted

## Context

The system has clearly separable concerns: authentication, subjects and plans,
document ingestion, retrieval, generation, auditing. Each could be a service.
One team builds and operates all of it.

## Decision

One deployable, divided into modules under `app/modules/`, each with the same
four layers: `presentation` (routes and schemas), `application` (use cases),
`domain` (rules and types), `infrastructure` (models and repositories).

Modules talk through their application layer, never by reaching into another
module's repositories.

## Consequences

- One process to run, one transaction to reason about. The audit trail can be
  written **inside the caller's own transaction**, which is what makes "no
  change without a trail" true rather than aspirational; across services that
  guarantee costs an outbox and eventual consistency.
- The layering is a convention, not a compiler rule. Nothing stops a route
  importing a repository directly, and code review is what keeps that from
  happening.
- The async work that genuinely needs to scale separately already does, through
  Celery workers running the same image. Scaling the API and the workers apart
  did not require splitting the codebase.
- A single deploy means a bad change affects everything at once.

## What would change this

- **A module with a different scaling shape.** Ingestion is the candidate: it
  is CPU-bound, minutes long, and shares a worker pool with tasks that take
  milliseconds. Splitting the queue comes first and is much cheaper than
  splitting the service.
- **More than one team.** The strongest argument for services is organisational,
  and it does not apply yet.
