# Scaling to 80,000 concurrent users at ≤300ms

Target: **80k simultaneous users, p95 ≤ 300ms** on the non-AI paths.

This is a capacity plan built on the measured numbers in `RESULTS.md`, not a
guess. Read `RESULTS.md` first — it is the evidence; this file is the arithmetic.

## The one conversion that matters: users → req/s

"80k users" is not a load figure until you say how often each one acts. From the
realistic run (a click every 5–10s):

```
750 users produced ~99 req/s  →  ~0.13 req/s per user
80,000 users × 0.13 req/s     ≈  10,600 req/s
```

So the real target is **~10,600 req/s at p95 ≤ 300ms**. Everything below sizes
for that. If real usage is burstier than "a click every 5–10s", scale the number
linearly — measure it in production, don't trust this constant blindly.

Today the app does **~150 req/s saturated on one core**. The gap is **~70×**. It
is a throughput problem, and the API is stateless, so throughput is bought with
copies, not a rewrite.

> **Status: step one is built and measured.** `UVICORN_WORKERS` and PgBouncer
> are in the stack. On the same 4-CPU budget, 4 workers served **2.11x** the
> requests of 1 worker with a p95 **2.67x** better and no failures. See the
> "Workers" section of `RESULTS.md`. The arithmetic below is unchanged; what
> changed is that the first multiplier is now a setting rather than a plan.

## Is linear scaling real? Yes — measured

One uvicorn worker on 1 CPU → **750 users / p95 545ms**.
Four workers on 4 CPUs → **1000 users / p95 77ms, 0 failures** (`RESULTS.md`).

Throughput tracked cores ~1:1 and latency *improved* with headroom. That is the
whole basis of this plan: add cores, get proportional throughput, as long as the
shared tiers (Postgres, Redis) keep up. The rest of this doc is about keeping
them up.

## Sizing the API tier

Budget one worker per core, ~180 req/s per worker (the measured per-core ceiling,
kept conservative):

```
10,600 req/s ÷ 180 req/s per core ≈ 60 cores of API
```

Add ~40% headroom for burst, deploys and one AZ failing → **~84 cores**, e.g.
**~21 API containers at 4 vCPU each**, behind Traefik (already load-balancing
`loadbalancer.server.port=8000`). Round up and run 24–30 replicas across ≥2 nodes.

This part is easy *because* the app is stateless: sessions are JWT cookies, not
server memory, so any replica serves any user. The hard part is everything they
share.

## The real bottlenecks (in the order they will bite)

### 1. Postgres connections — will break first, today

`max_connections=100`. Each API process opens `db_pool_size=10 + db_max_overflow=20`
= up to **30 connections**. That is **~3 API processes before Postgres refuses
connections** — long before CPU is the limit. At 60+ workers you would need 1,800
raw connections; Postgres cannot do that.

**Fix: a connection pooler (PgBouncer) in transaction mode.** It multiplexes
thousands of client connections onto ~100–200 real Postgres ones. Non-negotiable
at this scale. Then drop each app pool to `db_pool_size≈5` and point it at
PgBouncer. This is the first thing to add and it is cheap.

### 2. Postgres read capacity

At 10.6k req/s the mix is read-heavy (`GET /subjects`, `/plans`, `/auth/me`).
One primary won't serve that comfortably.

- **Read replicas** — route `GET`s to replicas, writes to the primary. The
  Service pattern makes the read/write split a clean change.
- **Cache hot reads in Redis** — `/auth/me` and the first page of
  `/subjects`/`/plans` are the same rows over and over; a short TTL cache turns
  most of the read traffic into Redis hits.
- Right-size the primary (CPU/IO/`shared_buffers`); ensure the ownership-scoped
  queries are all indexed (they are today — `ix_*_user_id`).

### 3. Redis

Rate-limit counters, sessions/cache, Celery broker on one instance becomes a
single point of contention. Split roles (a cache instance vs a broker instance)
and scale the hot one — Redis will do >100k ops/s per instance, so this is
tuning, not redesign.

### 4. Auth (argon2) — sharp edge, mostly dodged

argon2 is deliberately CPU-expensive. At steady state it barely shows (JWT
cookies last 15 min, so logins are rare relative to reads). But a **login storm**
— 80k people signing in at 9:00 — is its own spike: at ~1 login/core/second, that
is minutes of queue. Mitigate with a dedicated auth replica pool that can scale
independently, and consider tuning the argon2 cost. Measure it on purpose with
`AUTH_WEIGHT=3`.

### 5. Turn pool-exhaustion 500s into 503s

Today an overloaded pool returns **500** (`RESULTS.md`). Under autoscaling that
is both a lie (it's backpressure, not a bug) and unretryable. Return **503 +
`Retry-After`** so load balancers and clients back off correctly, and so real
bugs stay visible in Grafana. Small code change, big operational payoff.

## What does NOT need to change

- **The application code / architecture.** Stateless API, async I/O, Service
  pattern, JWT sessions — this is already the right shape for horizontal scale.
  No rewrite.
- **The AI paths.** Out of scope here and a completely different problem (queue +
  workers + provider quota + $$). 80k users anywhere near the planner is a
  provider-billing and queue-sizing question — see the root `README.md` — not
  this HTTP-tier plan.

## Order of work (do them in this order)

1. **PgBouncer** (transaction mode) + shrink app pools. Unblocks replica scaling.
   *Without this, step 4 hits a wall at ~3 replicas.*
2. **Redis cache** for `/auth/me` + hot list pages; **503 + Retry-After** on pool
   timeout.
3. **Read replicas** + route reads off the primary.
4. **Scale the API tier** to ~24–30 replicas / ~4 vCPU, and set `--workers` in
   the Dockerfile so each container actually uses its cores (it doesn't today).
5. **Load test each step on staging** with this harness at the real target:
   ```bash
   THINK_TIME_MIN=5 THINK_TIME_MAX=10 SHAPE=step \
     STEP_START=2000 STEP_USERS=2000 STEP_MAX=90000 STEP_SPAWN=500 \
     TARGET=https://staging... perf/run.sh
   ```
   Run locust distributed (multiple workers) — one locust box cannot generate
   10k req/s. And these numbers were captured on a noisy shared dev box; treat
   the shape as the finding and re-measure absolutes on real infra.

## Honest bottom line

- **Reachable?** Yes. Stateless API + managed Postgres/Redis scales to this;
  10.6k req/s is a normal mid-size deployment, not exotic.
- **By adding replicas alone?** No — Postgres connections (step 1) and read
  capacity (step 3) break first. Those two are the actual project.
- **A rewrite?** No. It's infrastructure and a handful of small code changes
  (pooling config, a cache, one status code), all validated with the load test
  you already have.
- **The ≤300ms?** Already comfortable with headroom — 1000 users hit p95 77ms on
  4 workers. Latency is not the risk; the shared data tier is.
