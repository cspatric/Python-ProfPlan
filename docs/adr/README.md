# Architecture decision records

One file per decision that was hard to make and would be expensive to revisit.

Not every choice belongs here. A record earns its place when someone six
months from now would look at the code, think "that is backwards", and be
right to think so without the reasoning. The commit message is where a change
is explained; this is where a **trade** is explained.

Each one says what was decided, what it costs, and what would make it wrong.
That last part matters most: a decision recorded without the conditions that
would reverse it is a rule, and rules outlive their reasons.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-modular-monolith.md) | A modular monolith, layered per module | Accepted |
| [0002](0002-embedding-model.md) | bge-m3 for embeddings, slow and multilingual | Accepted |
| [0003](0003-async-plan-drafting.md) | Draft plans in a worker, not in the request | Accepted |
| [0004](0004-soft-delete-cascade.md) | Soft delete, cascading by hand | Accepted |
| [0005](0005-csrf-double-submit.md) | Double-submit CSRF cookie, session-lived | Accepted |
| [0006](0006-llm-fallback-chain.md) | One gateway, four providers, a shared breaker | Accepted |

## Writing a new one

Copy the shape of any of these. Keep it to a page. Write it when the decision
is made, not afterwards: a record written later describes what you did, and
the useful part is what you were weighing at the time.
