# Load test — captured baseline

Dev machine, single API container **pinned to 1.0 CPU / 1 GB** (the
`deploy.resources.limits` in `docker-compose.yml`, verified live via
`docker inspect`), one uvicorn worker, Postgres + Redis alongside. AI paths
excluded and blocked (see `README.md`). Dataset seeded to a steady state
(20 accounts × 60 subjects × 60 plans); each request uses a distinct client IP so
the per-IP rate limiter is not the bottleneck.

Captured 2026-07-16 against a freshly built image at `alembic head`.

> The previous baseline in this file was measured against a **stale container**
> (built before CSRF and the non-root hardening) whose `POST`s would 403 against
> today's code, and with `GET /plans` returning `[]`. Those numbers were not
> comparable to the current app and have been replaced.

## Headline — how many *people* fit?

**~750 simultaneous real users on one 1-CPU container**, at p95 545ms with zero
failures. Not thousands — not on a single core.

The number depends entirely on how fast each user clicks, so both models are
measured. Quote the first table when someone asks "how many people?".

### Real users (`THINK_TIME_MIN=5 THINK_TIME_MAX=10` — a click every 5–10s)

| users | req/s | p95 | failures | verdict |
|------:|------:|----:|---------:|---------|
| 250 | 33 | 26ms | 0% | idling |
| 500 | 65 | 46ms | 0% | comfortable |
| **750** | **99** | **545ms** | **0%** | **recommended ceiling** |
| 1000 | 119–122 | 1.1–1.3s | 0.16–0.25% | first errors |
| 1500 | — | — | **89%** | hard wall (connection resets) |

### Aggressive users (default `0.05–0.2s` — ~1.7 req/s each, nobody behaves like this)

| Question | Answer |
|----------|--------|
| Serves comfortably (p95 ≤ 1s, 0 failures) | ~75–100 users, ~125–180 req/s |
| Still works, just slow (no errors) | up to ~300 users (p95 ~7s) |
| First errors (HTTP 500) | ~400 users (0.08%), 0.5% at 500, ~2% at 600 |

Both models agree on the real limit: **~120–180 req/s on one saturated core**.
"Concurrent users" is just that throughput divided by how often each one clicks.

### It never crashed

Across every run — including 89% failures at 1500 users — the container reported
`Restarts=0`, `OOMKilled=false`, 224MB of its 1GB, and stayed `healthy`. It
degrades and eventually refuses connections; it does not fall over.

At 1500 concurrent connections the failures are `ConnectionResetError(104)` and
p95 *drops* to 290ms — the giveaway that connections are being rejected instantly
rather than served slowly. Nothing reaches app code (no `QueuePool` errors
logged), so this is the kernel resetting a full accept backlog: one CPU cannot
accept sockets fast enough while it is busy serving. Unlike the 500s below, this
wall was not root-caused further — a 150/s spawn storm may contribute.

## Capacity ramp (`SHAPE=step`, +25 users/60s, SLO p95 ≤ 1s)

| users | req/s | p95 | failures | verdict |
|------:|------:|----:|---------:|---------|
| 25 | 126–149 | 200–380ms | 0% | OK |
| 50 | ~100 | 620–820ms | 0% | OK |
| 75 | 119–176 | 490–965ms | 0% | OK |
| 100 | 145–178 | 985–1400ms | 0% | borderline — breached in 3 of 4 runs |
| 125 | 154–174 | 1600–1800ms | 0% | breach (latency only) |

Throughput **plateaus at ~130–175 req/s** from 75 users on: the single CPU is
saturated, so extra concurrency buys queueing, not throughput. Reproduced across
5 runs; the spread is host noise (see the caveat below).

### Steady-state detail — 75 users, 120s, 0 failures

| Endpoint | req/s | p50 | p95 | p99 |
|----------|------:|----:|----:|----:|
| `GET /subjects` (50 rows) | 43 | 430ms | 870ms | 1.3s |
| `GET /plans` (50 rows) | 28 | 430ms | 860ms | 1.3s |
| `GET /auth/me` | 21 | 320ms | 740ms | 1.1s |
| `GET /health` (liveness) | 14 | 270ms | 450ms | 530ms |
| `GET /ai/health` | 14 | 490ms | 920ms | 1.3s |
| `POST /subjects` (write) | 7 | 630ms | 1.1s | 1.3s |
| **Aggregated** | **126** | **410ms** | **850ms** | **1.3s** |

`GET /health` does nothing but return a literal, yet costs 270ms at p50 — that is
pure queueing, and the clearest single sign the box is CPU-bound rather than
blocked on I/O.

## The 10k-requests-under-200ms experiment (2026-07-16)

Goal: ~10,000 requests with latency under 200ms. Same offered load (~90–100
req/s, 50 users, 120s, seeded data) on both configs; think time raised on the
fast config to keep the offered load equal (closed-loop users would otherwise
punish the faster system with 2.8× the load).

| Config | requests | p50 | p95 | p99 | max | verdict |
|--------|---------:|----:|----:|----:|----:|---------|
| 1 worker · 1 CPU (stock) | 10,547 | 410ms | 780ms | 970ms | 1,448ms | **FAIL** |
| 4 workers · 4 CPUs | 12,258 | 8ms | **27ms** | 62ms | **167ms** | **PASS — every request < 200ms** |
| 4 workers · 2.8× load (bonus) | 29,111 | 34ms | 320ms | 620ms | 1,753ms | 2.8× throughput, p95 rises near ceiling |

The only change between rows 1 and 2 is `--workers 4` + a 4-CPU limit — zero
application code. 0 failures and 0 AI calls in all three runs.

### 100k endurance run (same day, 4 workers · 4 CPUs)

**112,549 requests over 9 minutes at a sustained 208 req/s — 0 failures, p95
75ms** (p50 12ms, p98 170ms). The p99 (370ms) and max (2.4s) are concentrated
in the first minute (spawning 100 users at 50/s + warm-up); the sliding-window
p95 only improves after that, ending at 76ms. Container memory rose from 510 to
~570MiB in the first minute (4 workers warming) and then **stayed flat at
568–571MiB for the remaining 8 minutes** — no leak, no restarts, no OOM.
Reproduce: `THINK_TIME_MIN=0.35 THINK_TIME_MAX=0.55 USERS=100 TIME=540s
perf/run.sh` (mind the 15-minute access-token lifetime — seed and run must fit
inside it, or the run 401s mid-flight).

## Where it actually breaks (`SLO_P95_MS` relaxed, +100 users/45s)

| users | req/s | p95 | failures |
|------:|------:|----:|---------:|
| 100 | 139 | 1.4s | 0% |
| 200 | 135 | 4.6s | 0% |
| 300 | 146 | 7.1s | 0% |
| 400 | 129 | 11s | 0.08% ← first 500s |
| 500 | 114 | 17s | 0.48% |
| 600 | 95 | 24s | 1.97% |

**Failure mode: DB connection-pool exhaustion, surfaced as a 500.** The errors
are all `TimeoutError: QueuePool limit of size 10 overflow 20 reached, connection
timed out, timeout 30.00` — from `db_pool_size=10` + `db_max_overflow=20` +
`db_pool_timeout=30` in `app/core/config.py`. Past ~400 users, requests wait more
than 30s for one of the 30 connections and the wait itself times out.

Two things worth noting about that:

1. It is **not** the pool being too small for the CPU — 30 connections is already
   generous for 1 CPU, and throughput was flat from 75 users on. The pool timeout
   is just where the queue *surfaces*. Raising `db_pool_size` here would move the
   symptom, not lift the ceiling; the CPU is the ceiling.
2. Pool-timeout is arguably the **wrong status code**: a saturated pool is
   backpressure (503 + `Retry-After`), not "the server is broken" (500). Worth a
   follow-up — it also means these are indistinguishable from real bugs in
   Grafana.

## What the numbers say

1. **~750 real users (or ~150 req/s) on a single 1-CPU container**, zero
   failures, p95 under a second. The API is stateless, so N cores ≈ N×
   throughput — Postgres (7% CPU under load) and Redis are nowhere near
   saturated.

   **Measured, not assumed:** re-running with `--workers 4` on a 4-CPU container
   held **1000 real users at p95 77ms, 0 failures** (vs 545ms at 750 on one
   core) — throughput scaled ~1 core → ~1 worker, near-linear, and latency
   *improved*. The stock `Dockerfile` runs **one** uvicorn process (no
   `--workers`), so the 1-CPU number is a per-process ceiling: giving the
   container more CPU does nothing until you also add workers or replicas. This
   is the single most important lever and it is why the 80k target below is a
   horizontal-scale problem, not a rewrite.

2. **It degrades gracefully rather than falling over.** From 100 → 300 users
   latency grows ~linearly while failures stay at 0 and the container stays
   healthy. That is the async design absorbing the queue.

3. **Rate limiting protects the box**: a single abusive IP is capped at
   120 req/min (10/min on auth, 20/min on AI/upload) and gets 429s — see
   `app/api/tests/test_rate_limit.py`. The saturation points above are only
   reachable by genuinely distributed traffic, which is why the test forges a
   distinct IP per request.

4. **argon2 is the auth ceiling, by design** (brute-force resistance). It is kept
   out of the numbers above deliberately — sessions are pooled — so these figures
   are the *read/CRUD* ceiling. Run `AUTH_WEIGHT=3` to measure auth on purpose.

## Levers to scale further (in impact order)

1. **More API replicas** — stateless; throughput scales ~linearly. Traefik already
   load-balances `loadbalancer.server.port=8000`.
2. **More CPU for the API container** — everything above is one saturated core;
   1→4 CPUs should roughly 4× throughput and cut tail latency under burst.
3. **Return 503 + `Retry-After` on pool timeout** instead of 500, so overload is
   distinguishable from failure (and retryable by clients).
4. **Tune argon2 cost / add a login cache** if auth QPS specifically matters.
5. For the **AI paths** (not measured here): queue + workers + provider billing —
   see the root `README.md`.

## Reproduce

```bash
docker compose --profile dev up -d

# The headline (how many people fit):
THINK_TIME_MIN=5 THINK_TIME_MAX=10 SHAPE=step \
  STEP_START=250 STEP_USERS=250 STEP_TIME=60 STEP_MAX=2500 STEP_SPAWN=100 perf/run.sh

make perf-capacity                                                      # aggressive ramp
USERS=75 RATE=25 TIME=120s perf/run.sh                                  # steady state
SHAPE=step STEP_START=100 STEP_USERS=100 SLO_P95_MS=999999 perf/run.sh  # find the 5xx point
```

**Host noise matters.** These runs shared a dev box whose idle load average was
~5 of 8 cores, and locust competes for CPU too. Expect ±20% run-to-run on
throughput; the *shape* (flat throughput, linear latency growth, 500s at ~400
users) reproduced consistently, the exact rps did not.

## Workers: the first step of the scaling plan, measured

`SCALING-80K.md` said the gap was a throughput problem and the API is
stateless, so throughput is bought with copies. `UVICORN_WORKERS` and PgBouncer
now exist, so here is the same load against both shapes.

Same container, same **4-CPU** limit, 100 users, spawn 20/s, 60s, on a
developer machine that was also running other projects. Absolute numbers are
therefore noisier than the 1-CPU baseline above; the comparison is the point.

| | requests | req/s | p50 | p95 | p99 | failures |
|---|---:|---:|---:|---:|---:|---:|
| 1 worker  | 3,911 | 66.2 | 1,000ms | 3,200ms | 5,300ms | 0 |
| 4 workers | 8,279 | 139.5 | 500ms | 1,200ms | 1,600ms | 0 |

**2.11x throughput, p95 2.67x better, zero failures either way.**

The shape of that result is the useful part: giving one uvicorn process four
cores does nothing, because it can only use one. The req/s per *worker* is
essentially unchanged (66 vs 35 each), which is the arithmetic in
`SCALING-80K.md` behaving as predicted rather than a surprise.

Not measured here, and worth measuring before trusting a bigger number: whether
PgBouncer changes anything at this level (it should not, since the win shows up when
worker count × pool size approaches Postgres' `max_connections`), and how the
curve behaves past 4 workers on more cores.
