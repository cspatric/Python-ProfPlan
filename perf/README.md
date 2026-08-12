# Load / performance tests

These measure **how much traffic the architecture absorbs** on the paths that do
**not** call an LLM — HTTP + Postgres + Redis + auth session + CRUD + listing.
They are free to run repeatedly (no AI tokens spent).

## No AI requests — enforced, not just promised

`POST /plans` (planner), `POST /ai/ask`, `POST /rag/query`, `POST /documents`
and `POST /plans/{id}/generate` all spend tokens or pin the local Ollama CPU.
Every request in the test goes through `ApiUser.api()`, which **raises before
opening a socket** if the path is on that list (`_AI_SPEND_PATHS` in
`locustfile.py`). Adding a task that hits one fails the run instead of quietly
appearing on the bill.

That is also *why* those paths are excluded: their ceiling is the LLM provider
(Gemini quota / Ollama CPU), not this service. The load test covers everything
*around* the AI — the part this architecture is responsible for. How the AI path
scales (queue + workers + fallback) is discussed in the root `README.md`.

Note `GET /ai/health` **is** included and is safe: it reads provider rows and
circuit-breaker state from the DB, and calls no model.

## Run it

The stack must be up: `docker compose --profile dev up -d`

```bash
perf/run.sh                              # flat: 100 users, spawn 20/s, 60s
USERS=300 RATE=50 TIME=120s perf/run.sh  # flat, custom

# Capacity discovery — ramp until the SLO breaks, then report the ceiling:
SHAPE=step perf/run.sh
SHAPE=step STEP_START=25 STEP_USERS=25 STEP_TIME=60 STEP_MAX=300 perf/run.sh

# "How many PEOPLE fit?" — model a teacher clicking every 5-10s, not a bot:
THINK_TIME_MIN=5 THINK_TIME_MAX=10 SHAPE=step \
  STEP_START=250 STEP_USERS=250 STEP_MAX=2500 STEP_SPAWN=100 perf/run.sh

# Where does it actually error (not just get slow)? Relax the latency SLO:
SHAPE=step STEP_START=100 STEP_USERS=100 SLO_P95_MS=999999 perf/run.sh

# Measure argon2/auth throughput on purpose (off by default):
AUTH_WEIGHT=3 perf/run.sh
```

Results (CSV + HTML report) land in `perf/results/` (git-ignored — the session
pool there holds real JWTs, so keep it out of commits).

### Knobs

| Env | Default | Meaning |
|-----|---------|---------|
| `SHAPE` | `flat` | `flat` = hold `USERS`; `step` = ramp until SLO breach |
| `USERS` / `RATE` / `TIME` | 100 / 20 / 60s | flat-shape load (ignored by `step`) |
| `STEP_START` / `STEP_USERS` / `STEP_TIME` / `STEP_MAX` | 25 / 25 / 30 / 500 | the ramp |
| `SLO_P95_MS` / `SLO_FAIL_PCT` | 1000 / 1.0 | a step passes while both hold |
| `WARMUP_SECONDS` / `SETTLE_SECONDS` | 60 / 20 | unmeasured warm-up; per-step ramp discarded |
| `ACCOUNTS` | 20 | accounts in the session pool |
| `SUBJECTS_PER_ACCOUNT` / `PLANS_PER_ACCOUNT` | 60 / 60 | seeded rows per account |
| `THINK_TIME_MIN` / `THINK_TIME_MAX` | 0.05 / 0.2 | seconds a user pauses between requests; `5` / `10` models a real person |
| `AUTH_WEIGHT` | 0 | weight of the argon2 `AuthUser` |
| `UNIQUE_IPS` | 1 | `0` keeps one IP → measures the rate limiter instead |
| `SEED` | 1 | `0` reuses the previous dataset/pool |

## Method

- Runs the official `locustio/locust` image on the compose **backend** network,
  hitting the API container directly (`http://api:8000`).
- **Seeding first.** `perf/seed.py` runs inside the api container (it already
  has the DB creds and drivers), registers the account pool, and inserts
  60 subjects + 60 plans per account straight into Postgres. Plans can *only* be
  created through the AI planner, so without this `GET /plans` returns `[]` and
  22% of the traffic measures an empty query. It also drops the previous run's
  `load-%@load.example.com` rows so runs stay reproducible.
- **Sessions are reused, not re-created.** argon2 hashing is deliberately
  CPU-expensive; paying it on every user spawn would make *spawning* the
  bottleneck and hide the read ceiling. The pool is registered once up front and
  the cookies are reused. Use `AUTH_WEIGHT` to load auth on purpose.
- **CSRF is honoured** — the `csrf_token` cookie is mirrored into the
  `X-CSRF-Token` header on unsafe methods, exactly like the frontend. Without
  it every POST is a 403 and you measure the rejection path, not the write path.
- Each request carries a **distinct `X-Forwarded-For`** so the per-IP rate
  limiter is not the bottleneck — we want the *infrastructure* ceiling here. The
  limiter itself is covered by `app/api/tests/test_rate_limit.py`; set
  `UNIQUE_IPS=0` to measure it instead.
- The step shape **medians several probes per step** and discards each step's
  ramp, because a single 10s window is too noisy to rank steps by.

## Interpreting the numbers

- **RPS** — sustained requests/second across all endpoints.
- **p50 / p95 / p99** — latency percentiles; watch p95 climb as the ceiling nears.
- **Failures** — should stay ~0 until saturation. Rising 5xx = the DB connection
  pool or CPU is saturated → the point to add API replicas / tune the pool.

Three different questions, three different answers — don't conflate them:

1. *How many users does it serve **well**?* → the `SHAPE=step` default (p95 ≤ 1s).
2. *How many before it **breaks**?* → relax `SLO_P95_MS` and watch for 5xx.
3. *How many **people**?* → set `THINK_TIME_MIN/MAX` to `5`/`10` first.

The gaps are large (see `RESULTS.md`): the app gets slow long before it errors,
and it fits ~7× more *people* than it does bots, because the default virtual user
hammers ~1.7 req/s and a real teacher does not. **A "concurrent users" number
without its think time is meaningless** — the honest invariant is req/s.

**Caveat: results are only as quiet as the host.** These runs share a dev
machine with other stacks, and locust itself competes for CPU. Expect ±20% on
throughput between runs; check `uptime` before trusting a number, and compare
runs rather than quoting one in isolation.

See `RESULTS.md` for a captured baseline.
