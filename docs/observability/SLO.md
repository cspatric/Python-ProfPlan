# Service level objectives

The alert rules in `docker/prometheus/rules/profplan.yml` answer **is it up**.
These answer **is it keeping its promise**, which is a different question and
the only one a teacher would recognise.

An objective is useful only if it can be missed. Every number below is set
where breaching it means someone had a worse day, not where it flatters the
graph.

## The objectives

| | Objective | Window | SLI |
| --- | --- | --- | --- |
| **API availability** | 99% of requests answered without a 5xx | 30 days | `slo:api_error_ratio:rate1h` |
| **API latency** | 95% of requests answered within 500 ms | 30 days | `slo:api_fast_ratio:rate1h` |
| **Plan drafting** | 95% of plans drafted within 2 minutes | 30 days | `slo:plan_draft_fast_ratio:rate6h` |
| **Plan drafting** | under 5% of draftings fail outright | 30 days | `slo:plan_draft_failure_ratio:rate6h` |

### Why these three and not others

**Availability at 99%, not 99.9%.** This runs on one machine, with one
database, behind one reverse proxy. 99.9% means 43 minutes of downtime a month
and there is no redundancy anywhere to deliver it. Writing 99.9% would be
writing a number nobody intends to meet, which is worse than an honest one.

**Latency measured on everything, with nothing excluded.** Creating a plan used
to take a minute and would have needed an exemption; it now takes 50 ms because
the drafting moved to a worker (ADR 0003). So if anything in this SLI is slow,
it is a bug rather than a category, and carving out exceptions is how a latency
objective stops meaning anything.

**Drafting timed from the queue, not from the worker.** The teacher is waiting
through the queue too. Timing only the LLM call would show a healthy number
during exactly the incident this is supposed to catch: a backlog where every
individual draft is fast and every teacher is still waiting.

**Two minutes**, because a real drafting measured 20 seconds end to end. Two
minutes is roughly six times that: enough room for a slow provider and a retry,
tight enough that a queue building up trips it.

## What is not covered

Said plainly, because an SLO page that implies more coverage than it has is
the kind of document that gets believed:

- **Document ingestion has no objective.** It is minutes of work by design (an
  hour for a book, see ADR 0002), so "fast" is not the promise. The promise is
  that it finishes or says why, and that is enforced by the code rather than
  measured here. An objective on completion rate would be the honest addition.
- **Nothing measures whether the plans are any good.** Every objective here is
  about delivery. A plan drafted in 20 seconds from the wrong three chunks
  passes all of them.
- **The window is nominal.** These have not been running for 30 days, so no
  error budget has been consumed or observed yet. The first month is the one
  that tells you whether the numbers were set sensibly.

## How the alerts behave

They fire on **burn rate**, not on a threshold being touched. One slow minute
is not an incident; spending a month's budget in an afternoon is.

| Alert | Fires when | Severity |
| --- | --- | --- |
| `ApiAvailabilityBudgetBurningFast` | burning 14x the sustainable rate over 5 min and 1 h | critical |
| `ApiAvailabilityBudgetBurning` | burning 6x over 1 h and 6 h | warning |
| `ApiLatencyObjectiveMissed` | under 95% fast for an hour | warning |
| `PlanDraftingObjectiveMissed` | under 95% drafted in time over 6 h | warning |
| `PlanDraftingFailing` | over 5% of draftings failed outright | critical |

The two windows on each burn alert are deliberate: a short window alone fires
on a blip, a long window alone notices too late. Both have to agree.

## When one fires

**Availability burning.** Check `/ready` first, it names the dependency. Then
Loki for the 5xx: `{job="profplan"} |= "500"` with the `trace_id` from the log
line, which opens the span in Tempo.

**Latency missed.** Usually the database. Check `slo:api_requests:rate5m` for a
traffic spike, then PgBouncer's pool. If the requests are slow but the database
is idle, something is waiting on an external call inside a request, which
should not exist.

**Drafting missed.** Look at `profplan_celery_queue_depth` before anything
else: a backlog trips this while every individual draft is fine. If the queue is
short, it is the provider chain, and `profplan_llm_requests_total` by provider
and outcome says which one.

**Drafting failing.** `profplan_llm_all_providers_failed_total` separates a bad
provider from a broken machine, since the last provider in the chain is local.
The affected plans are visible: the run carries `FAILED` and the reason.

## Reading them

Prometheus at `:9090`, the recorded series are all prefixed `slo:`. They are
recording rules so the ratios are precomputed and a dashboard does not have to
re-derive a six-hour rate on every refresh.
