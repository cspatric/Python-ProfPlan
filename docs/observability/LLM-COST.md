# What the AI costs

Until now the gateway counted attempts and failures, which answers "is the AI
working" and not "what is it costing us". Those are different questions and the
second one has an awkward property: the application does not choose the model.
The fallback chain does, at runtime, and the same plan is a fraction of a cent
on the local model and a real amount on a frontier one. A number that does not
carry the model is not an answer.

## The three places the answer lives

**Metrics, for the trend.** Per provider *and model*:

| metric | what it is |
| --- | --- |
| `profplan_llm_tokens_total{provider,model,direction}` | tokens as the provider reported them, input and output apart |
| `profplan_llm_cost_usd_total{provider,model}` | list price applied to those tokens |
| `profplan_llm_latency_seconds{provider,model}` | time to a completion |
| `profplan_llm_unpriced_calls_total{provider,model}` | calls on a model with no price in the table |

**The database, for one run.** `plan_generation` carries `llm_calls`,
`llm_input_tokens`, `llm_output_tokens` and `llm_cost_usd`, accumulated across
everything a plan did: the planner, a repair attempt, the judge, and one call
per activity across several workers. The API returns them under `usage` on the
generation response, so "what did this plan cost" needs no SQL.

**Loki, for one call.** Every successful completion logs `llm call` with the
provider, the model, both token counts, the cost and the latency. The prompt is
deliberately absent: it holds the teacher's material.

## Two decisions worth knowing

**An unpriced model is not free.** `cost_usd` returns `None` for a model that is
not in [`pricing.py`](../../app/modules/ai/domain/pricing.py), and `0.0` only
for a local one. Counting an unknown model as zero would make a cost report
that quietly balances while missing part of the invoice, so the unknown case
gets its own counter and its own alert. This is not hypothetical: the first
real run after this was written used `gemini-flash-lite-latest`, an alias that
was not in the table, and the counter is how anybody knew.

**The accumulation happens in the database.** A dozen item workers finish at the
same time; a read-modify-write in Python would drop most of them. `UPDATE ...
SET llm_cost_usd = llm_cost_usd + :n` cannot. Under-reporting is the worst
failure mode for a cost report, because it looks like good news.

## The worker is where the AI runs

Every LLM call the product makes is inside a Celery task, so before this the
metrics existed and nothing scraped them, which is the same as not having them.
The worker now serves `/metrics` on **:9200**, merged across its pool processes
through `PROMETHEUS_MULTIPROC_DIR`, and Prometheus has a `worker` job.

Two forks caught here, both worth remembering:

- prometheus_client keeps a registry per process, so without the multiprocess
  directory the endpoint would report whichever child answered. It refuses to
  serve rather than report that.
- the JSON log handler writes through a `QueueListener`, which is a thread, and
  threads do not survive a fork. The pool processes inherited the queue and no
  reader, so everything a task logged went in and stayed there. Logging is set
  up again in `worker_process_init`.

## Alerts

`LLMSpendJumped` fires on spend five times the last six hours' average, not on
an absolute budget, which is a business decision nobody has written down. The
shape is what matters: a jump means either a burst of plans or a chain falling
through to a dearer model.

`LLMModelHasNoPrice` fires on any unpriced call, because every one of them
makes the total quietly smaller than the bill.

## Measured on 2026-08-14

Three real plans through the whole stack, no mocks:

| | |
| --- | --- |
| a plan of 4 activities | 14 calls, 5.252 in, 22.627 out |
| a plan of 3 activities | 10 calls, 4.138 in, 16.097 out, **0.006853 USD** |
| median latency per call | 6.8 s on `gemini-flash-lite-latest` |
| unpriced calls, first run | 14, which is how the missing alias was found |
| unpriced calls, after | 0 |

Roughly two tenths of a cent per activity on a cheap model. The same plan on
Sonnet, at 3 and 15 USD per million, would be about 0.35 USD, fifty times more.
That ratio is the reason every one of these metrics carries the model.
