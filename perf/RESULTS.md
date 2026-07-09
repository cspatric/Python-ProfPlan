# Load test — captured baseline

Dev machine, single API container **pinned to 1.0 CPU / 1 GB** (the
`deploy.resources.limits` in `docker-compose.yml`), Postgres + Redis alongside.
AI paths excluded (see `README.md`). Each request uses a distinct client IP so
the per-IP rate limiter is not the bottleneck.

Reproduce: `USERS=80 RATE=4 TIME=90s perf/run.sh`

## Result — 80 concurrent users, 90s, 0 failures

| Endpoint | req/s | p50 | p95 | p99 |
|----------|------:|----:|----:|----:|
| `GET /subjects` (list) | 56 | 230ms | 640ms | 1.7s |
| `GET /plans` (list) | 38 | 230ms | 660ms | 1.7s |
| `GET /auth/me` | 29 | 200ms | 580ms | 1.2s |
| `GET /ai/health` | 19 | 230ms | 650ms | 2.2s |
| `GET /health` (liveness) | 19 | 56ms | 120ms | 600ms |
| `POST /subjects` (write) | 11 | 280ms | 2.5s | 5.3s |
| `POST /auth/register` (argon2) | 0.9 | 2.2s | 7.6s | 9.4s |
| **Aggregated** | **173** | **210ms** | **670ms** | **2.6s** |

Under a hard 100-user burst (spawn 25/s) the same stack sustained **530 req/s**
aggregate with **0 infrastructure errors** — latency degraded gracefully (no
5xx, no timeouts), which is the queue/async design doing its job.

## What the numbers say

1. **~170 req/s mixed traffic on a single 1-CPU container**, zero failures.
   Reads sit at p50 ~230ms / p95 <700ms under load. Linear headroom: the API is
   stateless, so N replicas ≈ N× throughput (Postgres/Redis are far from
   saturated here).

2. **The bottleneck is `argon2` password hashing**, by design. It's deliberately
   CPU-expensive (brute-force resistance). A burst of simultaneous
   registrations/logins on **one CPU** serializes behind it (register p50 jumped
   from 2.2s → 14s when 100 users hit at once). This is an *auth* ceiling, not a
   read ceiling — and it's the right trade-off (security over raw auth QPS).

3. **Rate limiting protects the box**: a single abusive IP is capped at
   120 req/min (10/min on auth, 20/min on AI/upload) and gets 429s — verified
   live and in `app/api/tests/test_rate_limit.py`. So the "one client floods us"
   scenario can't reach these saturation points in the first place.

## Levers to scale further (in impact order)

1. **More API replicas** — stateless; throughput scales ~linearly. Traefik
   already load-balances `loadbalancer.server.port=8000`.
2. **Give the API container more CPU** — argon2 auth is CPU-bound; 1→4 CPUs
   roughly 4×'s auth throughput and cuts read tail latency under burst.
3. **Tune argon2 cost / add a login cache** if auth QPS specifically matters.
4. For the **AI paths** (not measured here): queue + workers + provider billing —
   see the root `README.md`.
