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

## The monthly budget

`LLM_MONTHLY_BUDGET_USD` (5 by default, 0 turns it off) is what one account may
spend on the AI in a calendar month, at list price. The rate limits cap
requests per minute, which is a different thing: a request a minute on an
expensive model is still a bill at the end of it.

**Checked at the door, once per plan, not per LLM call.** A run that has
started finishes. Stopping halfway leaves a plan with three activities written
and five empty, which costs the tokens already spent and delivers nothing. The
overshoot is bounded by one plan.

**402, not 429.** This is not "too fast", it is "no more money this month", and
a client that retries a 429 in a minute would be doing exactly the wrong thing.
The message says when it resets, because an error that does not say what to do
next is a support ticket.

Both doors are covered: `POST /plans` (which drafts in the background) and
`POST /plans/{id}/generate`.

| endpoint | who | what it answers |
| --- | --- | --- |
| `GET /api/v1/usage/me` | the account itself | spent, budget, remaining |
| `GET /api/v1/usage` | admin only | every account, dearest first |

The account can see its own limit on purpose: a limit somebody cannot see is a
limit they can only discover by hitting it.

## Seeing it in Grafana

**http://localhost:3000/d/profplan-ai-cost** (admin/admin locally), provisioned
from `docker/grafana/dashboards/profplan-ai-cost.json`.

The top half is per account and comes from **the database**; the bottom half is
trends and comes from **Prometheus**. That split is deliberate: a per-user label
on a Prometheus counter is an unbounded number of time series, and the first
thing it breaks is Prometheus itself. Trends belong in metrics, "who spent
what" belongs in a table.

Grafana reads the database as `grafana_ro`, a role that can only SELECT
(`docker/postgres/init-grafana-role.sh`). A dashboard with the application's
own credentials is one bad panel away from a DELETE. For a database that
already exists, the role is created with:

```sql
CREATE ROLE grafana_ro LOGIN PASSWORD 'the value of GRAFANA_DB_PASSWORD';
GRANT CONNECT ON DATABASE profplan TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
```

| panel | question |
| --- | --- |
| Spend this month | what is this costing in total |
| Cost per plan | the number to quote when somebody asks |
| Who is spending it | per account: runs, tokens, USD |
| Budget used | how close each account is to being refused |
| Cost rate by model | why the bill changed, which is usually the model |
| The dearest runs | one row per plan, to take into Loki |

To go from a row to the calls behind it, Explore in Loki with
`{container="backend-worker-1"} | json | llm_cost_usd != ""`.

### Where a Bedrock price comes from

Not from memory. Every model on Bedrock carries an agreement offer with a rate
card on it, and it is readable:

```bash
curl -H "Authorization: Bearer $BEDROCK_API_KEY" \
  https://bedrock.us-east-1.amazonaws.com/list-foundation-model-agreement-offers/anthropic.claude-sonnet-5
```

That is how the Sonnet 5 entry was written, and it is why it is *not* the 4.x
price: 2,20 in and 11,00 out per million in us-east-1 on demand, against 3 and
15 for the 4.x family. Through the `global.` profile it is 2,00 and 10,00. The
routing prefix is stripped before the table is consulted, so the dearer of the
two is quoted; for a cost report, over-reporting is the right direction to be
wrong in.

The offer only lists while the agreement is not yet accepted, so read it before
switching a model on, not after.

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

## Measured with two accounts on 2026-08-16

Two teachers and a coordinator, three plans:

| account | runs | tokens | USD |
| --- | --- | --- | --- |
| ana@escola.example | 1 | 18.142 | 0,0061 |
| bruno@escola.example | 2 | 20.243 | 0,0053 |

`GET /usage/me` as Ana returned `{"spent_usd": 0.006099, "budget_usd": 5.0,
"remaining_usd": 4.993901}`; the admin listing returned both accounts ranked by
spend; Ana asking for the admin listing got 403. With the budget lowered to
0,005 USD, her next plan was refused with 402 and *no plan row was written*.

## Bedrock, and what it costs compared to the rest

Switched on 2026-08-16. Both things a new provider has to get right are done
and both were already watched: it reports usage (Converse returns `usage`, and
the cached-token counts are added in rather than dropped, since they are
billed), and its model ids are in the price table, with the `us.` / `global.`
routing prefix stripped first because it decides which region serves the
request, not what it costs.

The number worth staring at, one plan of the same shape on each model:

| model | calls | tokens | USD | plans per teacher at the 5 USD cap |
| --- | --- | --- | --- | --- |
| `gemini-flash-lite-latest` | 10 | 20.235 | **0,0069** | ~700 |
| `us.anthropic.claude-haiku-4-5` (Bedrock) | 8 | 23.257 | **0,1103** | ~45 |
| `us.anthropic.claude-sonnet-4-6` (Bedrock) | 11 | 57.120 | **0,7899** | ~6 |

Two things the table says that a price list does not. The gap between the ends
is a hundred and fifteen times, and it is not only the price per token: the
better model writes far more, 57 thousand tokens against 20 thousand for the
same plan. And Haiku sits at a seventh of Sonnet while still being Claude,
which is the trade most deployments actually want.

Which one is right is a product decision. This page exists so that it can be
made with the numbers in front of somebody instead of from a feeling about
model names.

### Two tiers, and what the cheap one costs in substance

One plan is not one kind of work. The roadmap is a single call that decides
what all the activities will be about; a bad roadmap makes eight good
activities about the wrong things. Writing one activity is bulk drafting
against a decision already made, and it is where the tokens are.

So there are two chains (`LLM_STANDARD_CHAIN`, `LLM_FAST_CHAIN`) and each
provider may carry a cheap model of its own (`*_FAST_MODEL`). Measured on the
same subject:

| strategy | calls | tokens | USD | chars per activity | headings per activity |
| --- | --- | --- | --- | --- | --- |
| everything on Haiku 4.5 | 8 | 23.257 | 0,1103 | 7.965 | 55,7 |
| Haiku decides, Nova Lite writes | 7 | 10.644 | **0,0125** | 3.391 | 23,7 |

**Nine times cheaper, and less than half the material.** That second number is
the one a price table cannot tell you: the activities the cheap model wrote are
coherent, structured and in good Portuguese, and they are thinner. Whether that
is a saving or a downgrade is a judgement about the product, not about the
bill, and it is why both numbers are here.

The knob is per provider, so the split can be moved without touching code: a
deployment that finds Nova Lite too thin can set `BEDROCK_FAST_MODEL` to Haiku
and keep the two-chain structure for the day a cheaper model is good enough.

**On which model, and where.** Anthropic's generation 5 (Sonnet 5, Opus 5) is
not available to every account: the error is
`not available for this account ... contact AWS Sales`, and it is neither the
inference profile nor the agreement, since Haiku 4.5 and Opus 4.5 answer with
their agreements equally `NOT_AVAILABLE`. It is an account-level entitlement
and the route is an AWS Support case, not a console button.
