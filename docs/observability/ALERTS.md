# Alerts and what to do about them

Prometheus evaluates the rules in [`docker/prometheus/rules/`](../../docker/prometheus/rules/)
every 15 seconds and hands anything firing to Alertmanager, which groups it,
suppresses the noise and routes it to a receiver.

```
app /metrics ─┐
flower        ├─▶ Prometheus ──(rules)──▶ Alertmanager ──▶ receiver
node-exporter ┘      :9090                   :9093          (see below)
```

| Where to look | URL |
|---|---|
| Rules and their current state | http://localhost:9090/alerts |
| What is firing right now, grouped | http://localhost:9093 |
| The dashboard behind these numbers | http://localhost:3000/d/profplan-overview |

Start it all with `make up`, or `docker compose --profile observability up -d`
for the monitoring side alone.

## The pipeline is only as good as its heartbeat

`Watchdog` fires permanently, on purpose, and is routed to a receiver that
discards it. Its job is to prove the whole path works: rule evaluation,
Alertmanager, routing. **If Watchdog stops arriving, every other alert here is
silently useless**, which is the failure mode that makes teams believe they are
monitored when they are not. Point a dead-man's-switch service at it if you
ever want that guarantee automated.

## Sending alerts somewhere

Out of the box alerts stop at the Alertmanager UI. Nothing is pushed, and no
secret is needed to get that far. To send them to Slack:

1. Create an incoming webhook in Slack.
2. Write the URL, and nothing else, into `docker/alertmanager/slack_api_url`
   (git-ignored).
3. Uncomment the `slack_configs` block in
   [`docker/alertmanager/alertmanager.yml`](../../docker/alertmanager/alertmanager.yml)
   and restart: `docker compose restart alertmanager`.

---

## The alerts

### ApiDown

**Severity: critical.** Prometheus could not scrape `api:8000/metrics` for a
minute. Either the container is gone, or it is so saturated it cannot answer.

First: `docker compose ps api` and `docker compose logs --tail=100 api`. If the
container is up and healthy, the API is saturated rather than dead, so check
CPU on the host panel and the request rate: this is what the load test's hard
wall looks like from the outside.

While this fires, alerts about dependencies and latency are suppressed by an
inhibit rule, because they would all be consequences of the same thing.

### HighServerErrorRate

**Severity: critical.** More than 2% of requests returned 5xx over five
minutes. This is a ratio, not a count, so it means the same thing at 50 req/s
and at 5000.

First: Grafana, *Busiest routes*, to see whether it is one endpoint or all of
them. Then Loki for the actual errors:

```
{container="backend-api-1"} | json | status >= 500
```

One route means a bug; every route means a dependency. Check `DependencyDown`
before you go reading code.

### LatencyP95Degraded

**Severity: warning.** p95 above one second for ten minutes, measured across
the whole API from the high-resolution histogram.

The captured baseline is **p95 545 ms at 750 concurrent users on one core**
(see [`perf/RESULTS.md`](../../perf/RESULTS.md)), so this means you are past the
measured ceiling. Either load grew or something got slower. Take a `trace_id`
from a slow request's log line and open the trace in Tempo: it will say whether
the time is in our code, in Postgres, or in an LLM call.

The documented fix for the load case is more Uvicorn workers plus PgBouncer,
not application changes.

### DependencyDown

**Severity: critical.** The API's background probe could not reach Postgres or
Redis for two minutes. `/ready` is returning 503, so a load balancer should
already have stopped sending traffic.

`{{ $labels.dependency }}` tells you which one. Then
`docker compose ps postgres redis` and their logs. Redis being down also stops
the queue, the rate limiter and the circuit breakers from working, so expect
company.

### CeleryQueueBacklog

**Severity: warning.** More than 100 messages waiting for ten minutes. Work is
arriving faster than the worker drains it: documents stay in `processing`,
generated items stay `pending`.

Check Flower (http://localhost:5555) for what is running and how long tasks are
taking. A slow LLM provider makes `generation.run_item` pile up; a large
document does the same for ingestion. If it is sustained rather than a spike,
add worker concurrency.

### CeleryQueueStalled

**Severity: critical.** The queue is not empty and **no task has succeeded in
fifteen minutes**. That is not a busy period, it is a stuck or dead worker.

`docker compose logs --tail=200 worker`. Look for a crash loop, or for the
event-loop errors the `NullPool` engine and the per-run Redis client exist to
prevent. Because tasks ack late, restarting the worker re-delivers whatever was
in flight, and the idempotency guard makes that safe.

### CeleryTaskFailures

**Severity: warning.** Tasks are failing *after* exhausting their retries, so
a document or a generated item is now `FAILED` and a user can see it.

Flower shows the traceback and the arguments. For ingestion the error is also
stored on the row and served by `GET /documents/{id}/status`.

### LlmAllProvidersFailing

**Severity: critical.** More than three generations in fifteen minutes failed
on *every* provider, local Ollama included. Plan creation is returning 503 and
`POST /plans` fails before persisting anything, so no half-plans are being
created.

Check `GET /api/v1/ai/health` first: it reports each provider's status and
whether its circuit is open. If the cloud providers are out of credit or
blocked, the fallback should have landed on Ollama, so Ollama failing too
usually means the model was never pulled (`make pull-model`) or the container
is down.

### LlmProviderCircuitOpen

**Severity: warning.** Requests are skipping a provider because its breaker is
open, and falling through to the next one. Answers still work; they cost more
and take longer.

Expected during a provider outage, and it closes itself after the cooldown once
a trial call succeeds. Worth investigating if it is the first provider in the
chain and it stays open: check the API key and the provider's status page.

### HostDiskFillingUp

**Severity: critical.** Less than 10% free on `/`. Postgres, MinIO, Loki,
Prometheus and Grafana all write there, and a full disk stops writes and can
corrupt them.

`docker system df` is usually the answer: old images and build cache.
`docker system prune -a` reclaims most of it. Check volume growth too, since
`chunks` and Loki's log store both grow with use.

### HostMemoryPressure

**Severity: warning.** Less than 10% memory available for ten minutes. The next
spike starts OOM-killing containers, and the one it picks will not be the one
you would have chosen.

---

## Known gaps

- **Worker-side LLM metrics are not scraped.** `profplan_llm_requests_total`
  is incremented in the Celery worker too, but the worker has no HTTP server,
  so those counts never reach Prometheus. The gateway numbers on the dashboard
  are API-process only. Closing this needs a pushgateway or a Celery exporter.
- **Flower is not in the observability profile.** It runs under `dev` and
  `production`, so with only the observability profile up, the Celery panels
  and `CeleryTaskFailures` have no data. That is deliberate: no rule alerts on
  Flower being absent.
- **No paging.** The default receiver discards. Alerts are real and visible;
  routing them to a human is the Slack step above.
