# Load / performance tests

These measure **how much traffic the architecture absorbs** on the paths that do
**not** call an LLM — HTTP + Postgres + Redis + auth session + CRUD + listing.
They are free to run repeatedly (no AI tokens spent).

## Why the AI paths are excluded

`POST /plans` (planner) and `POST /ai/ask` are bounded by the **LLM provider**,
not by this service: Gemini's rate/quota and Ollama's CPU are the ceiling. Load
testing them would cost money and would only measure the provider. So the load
test covers everything *around* the AI — the part this architecture is actually
responsible for. How the AI path scales (queue + workers + fallback) is discussed
in the root `README.md`.

## What is measured

| Endpoint | Path | Cost |
|----------|------|------|
| `GET /subjects` | list (DB read, ownership-scoped) | cheap |
| `GET /plans` | list (DB read) | cheap |
| `GET /auth/me` | session-authenticated read | cheap |
| `GET /ai/health` | provider status (DB + circuit state) | cheap |
| `GET /health` | liveness | trivial |
| `POST /subjects` | create (DB write) | cheap |
| `POST /auth/register` + `/login` | argon2 hash (deliberately heavy) | at user start only |

## Method

- Runs the official `locustio/locust` image on the compose **backend** network,
  hitting the API container directly (`http://api:8000`).
- Each request carries a **distinct `X-Forwarded-For`** so the per-IP rate
  limiter is not the bottleneck — we want the *infrastructure* ceiling here. The
  limiter itself is covered by `app/api/tests/test_rate_limit.py`.

## Run it

```bash
# stack must be up:  docker compose --profile dev up -d
perf/run.sh                          # 100 users, spawn 20/s, 60s
USERS=300 RATE=50 TIME=120s perf/run.sh
```

Results (CSV + HTML report) land in `perf/results/` (git-ignored).

## Interpreting the numbers

- **RPS** — sustained requests/second across all endpoints.
- **p50 / p95 / p99** — latency percentiles; watch p95 climb as the ceiling nears.
- **Failures** — should stay ~0 until saturation. Rising 5xx/timeouts = the DB
  connection pool or CPU is saturated → the point to add API replicas / tune the
  pool.

See `RESULTS.md` for a captured baseline on the dev machine.
