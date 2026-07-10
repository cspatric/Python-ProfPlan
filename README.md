# Python-ProfPlan

ProfPlan backend — AI/RAG-powered teaching plans platform.

Modular architecture with FastAPI, PostgreSQL/pgvector, Redis, Celery, MinIO and
an observability stack (Prometheus, Loki, Grafana, Traefik).

## Architecture

The codebase follows a **layered / Clean Architecture** style that borrows the
folder structure of DDD — it is **DDD-inspired, not full DDD**. We use the four
layers (and services), but not the complete set of DDD rules (no formal
aggregates, value objects or a strict ubiquitous language).

Each feature lives under `app/modules/<feature>/` with four layers:

| Layer | Folder | Responsibility |
|-------|--------|----------------|
| Presentation | `presentation/` | HTTP routers, request/response schemas, dependencies |
| Application | `application/` | Use-case **services**, commands/queries, DTOs |
| Domain | `domain/` | Business rules: entities, enums, interfaces, exceptions, events |
| Infrastructure | `infrastructure/` | SQLAlchemy models, repositories, external adapters |

Routers never touch the database directly — they call a service, which uses
repositories.

## Stack

The whole infrastructure runs with a single Docker Compose file (one container
per responsibility):

| Service | Image | Purpose | Local port |
|---------|-------|---------|------------|
| traefik | `traefik:v3.3` | Edge router / reverse proxy | 80, 443 |
| api | built (`docker/api`) | FastAPI application | via traefik (`api.localhost`) |
| worker | same image as api | Celery worker (background jobs) | — |
| flower | same image as api | Celery monitoring dashboard | 5555 |
| postgres | `pgvector/pgvector:pg17` | Database + pgvector (not exposed) | — |
| redis | `redis:8-alpine` | Cache + Celery broker/backend | — |
| minio | `minio/minio` | S3-compatible object storage | 9000, 9001 (console) |
| ollama | `ollama/ollama` | Embedding model server (bge-m3) | — |
| prometheus | `prom/prometheus` | Metrics | 9090 |
| grafana | `grafana/grafana` | Dashboards (metrics, logs, traces) | 3000 |
| loki | `grafana/loki` | Log aggregation | 3100 |
| promtail | `grafana/promtail` | Ships all container logs to Loki | — |
| node-exporter | `prom/node-exporter` | Host metrics (CPU, memory, disk, network) | 9100 |
| tempo | `grafana/tempo` | Distributed traces backend | — |
| otel-collector | `otel/opentelemetry-collector-contrib` | Telemetry pipeline | 4317, 4318 |
| adminer | `adminer` | DB UI (development only) | 8081 |

Two networks: `frontend` (edge, Traefik ↔ API) and `backend` (internal —
PostgreSQL is never exposed to the host). Named volumes persist Postgres, Redis,
MinIO and Grafana data.

### Tracing (OpenTelemetry)

Distributed tracing is opt-in (`OTEL_ENABLED=true`) and needs the
`observability` profile (otel-collector + **tempo**). The API and Celery worker
auto-instrument FastAPI, SQLAlchemy, Redis, httpx and Celery, exporting spans to
the collector → Tempo → Grafana (Tempo datasource is pre-provisioned). Context
propagates across the Redis broker, so a document upload and its background
ingestion (parse → embed → index) appear in a **single trace**.

### Logging (structured → Loki)

Every process logs single-line **JSON** to stdout (`LOG_LEVEL` controls the
level). Promtail discovers all containers via the Docker socket and ships their
logs to Loki, queryable in Grafana (Explore → Loki), e.g.
`{container="backend-api-1"} | json | user_id="..."`.

A `RequestLoggingMiddleware` emits one line per HTTP request with rich context —
method, path, status, latency, client IP, user agent, the **acting user**
(`user_id`/`user_email`/`user_role`) and the `trace_id`, so a log line links
straight to its span in Tempo. Unhandled and 5xx errors are recorded on the
active span (exception + stacktrace).

### Metrics (Prometheus)

The API exposes `/metrics` (HTTP request rate, latency and status via
`prometheus-fastapi-instrumentator`). Prometheus also scrapes **node-exporter**
for host metrics (CPU, memory, disk, network) and the OTel collector.

> This repository is **backend-only**. The React frontend lives in a separate
> repository and is intentionally not part of this stack.

## Running the environment

```bash
cp .env.example .env   # fill in the values
make certs              # self-signed TLS cert for Traefik's :443 listener
```

The stack uses Docker Compose **profiles**:

```bash
docker compose --profile dev up --build                       # core + adminer
docker compose --profile production up -d                     # core only
docker compose --profile dev --profile observability up -d    # everything
docker compose run --rm lint                                  # run Ruff (lint/PEP 8)
```

### Service URLs

Once the stack is up, each service is reachable at:

| Service | URL | Notes |
|---------|-----|-------|
| API (FastAPI) | http://api.localhost/health, https://api.localhost/health | Via Traefik. Add `127.0.0.1 api.localhost` to your hosts file, or send `Host: api.localhost` header. HTTPS uses the self-signed cert from `make certs` — expect a browser warning locally |
| Traefik dashboard | _not exposed by default_ | The old unauthenticated `:8080` listener is off (`api.insecure: false`). Uncomment the basic-auth `dashboard` router in `docker/traefik/dynamic.yml` to re-enable it safely |
| Flower (Celery) | http://localhost:5555 | Celery task monitoring — tasks, queues, failures, workers (task-level detail Prometheus doesn't give) |
| Grafana | http://localhost:3000 | Default login `admin` / `admin` (Prometheus + Loki + **Tempo** datasources pre-provisioned) |
| Prometheus | http://localhost:9090 | Metrics |
| MinIO console | http://localhost:9001 | Login with `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` from `.env` |
| MinIO API (S3) | http://localhost:9000 | S3-compatible endpoint |
| Adminer | http://localhost:8081 | DB UI — server `postgres`, credentials from `.env` |
| Loki | http://localhost:3100 | Log API (`/ready`, `/loki/api/...`) |
| OTel Collector | grpc `localhost:4317` / http `localhost:4318` | OTLP ingest (traces/metrics/logs) |
| Tempo (traces) | _not exposed to the host_ | Distributed traces backend — view them in Grafana (Explore → Tempo). `observability` profile |
| Ollama (embeddings) | _not exposed to the host_ | Serves the **bge-m3** model. Pull once: `docker compose exec ollama ollama pull bge-m3` |
| PostgreSQL | _not exposed to the host_ | Reachable only inside the `backend` network |
| Redis | _not exposed to the host_ | Reachable only inside the `backend` network |

> `observability` services (Grafana, Prometheus, Loki, OTel Collector, Tempo)
> require the `--profile observability`; Ollama runs under `dev`/`production`.

To add the API host entry on Linux/macOS:

```bash
echo "127.0.0.1 api.localhost" | sudo tee -a /etc/hosts
```

To stop everything (volumes/data are kept):

```bash
docker compose --profile dev --profile observability down
```

## Linting & formatting

Linting (PEP 8) and formatting are handled by [Ruff](https://docs.astral.sh/ruff/),
run through Docker — no local Python install required. Configuration lives in
`pyproject.toml` under `[tool.ruff]`.

```bash
./scripts/lint.sh          # check for lint / PEP 8 issues
./scripts/lint.sh --fix    # auto-fix what can be fixed
./scripts/format.sh        # format the code
./scripts/format.sh --check # verify formatting without writing
```

## Database migrations (Alembic)

Every schema change goes through an Alembic migration — never edit the database
by hand. Run Alembic inside the `api` container:

```bash
# create a migration from model changes
docker compose exec api alembic revision --autogenerate -m "feat description"
# apply migrations
docker compose exec api alembic upgrade head
# roll back the last migration
docker compose exec api alembic downgrade -1
```

When you add a new module with tables, import its models in `alembic/env.py` so
autogenerate can see them.

## Authentication

Cookie-based JWT authentication (login only for now; OAuth providers are
modelled for later). Endpoints under `/api/v1/auth`:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Authenticate with email/password, sets cookies |
| POST | `/auth/refresh` | Rotate the refresh token, re-issues cookies |
| POST | `/auth/logout` | Revoke the current session |
| POST | `/auth/logout-all` | Revoke every session of the user |
| GET | `/auth/me` | Return the authenticated user |

Security properties:

- **Access token** JWT (15 min) and **refresh token** JWT (30 days), the latter
  stored only as a SHA-256 hash in `refresh_tokens`.
- **HttpOnly** cookies, `Secure` (set `COOKIE_SECURE=true` behind HTTPS) and
  `SameSite`.
- Passwords hashed with **Argon2id**.
- **Rotating** refresh tokens — each refresh revokes the old session and issues a
  new one; presenting a revoked token triggers reuse detection and revokes all
  sessions.
- Session revocation (single device or all).
- **Rate limiting** on login via Redis.
- Authentication **audit log** (`auth_logs`).

Create a user (development helper):

```bash
docker compose exec -e PYTHONPATH=/app api \
  python scripts/create_user.py user@example.com "Full Name" "Password@123"
```

## Domain resources

All resource routes require the auth cookie; `user_id` comes from the
authenticated user and every query is scoped to that user.

| Resource | Base path | Notes |
|----------|-----------|-------|
| Subjects | `/api/v1/subjects` | Full CRUD |
| Plans | `/api/v1/plans` | Full CRUD; `subject_id` must belong to the user |
| Modules | `/api/v1/modules` | Full CRUD; `plan_id` must belong to the user; list is filtered by `plan_id` |
| Academic items | `/api/v1/academic-items` | Full CRUD; `module_id` must belong to the user; list filtered by `module_id`; **soft delete** |
| Academic item categories | `/api/v1/academic-item-categories` | Global catalog, full CRUD |
| Academic item category types | `/api/v1/academic-item-category-types` | Global catalog, full CRUD; `academic_item_category_id` must exist; list filterable by `category_id` |
| Documents | `/api/v1/documents` | Multipart **upload** (202) → stored in MinIO + queued for async ingestion; list (`?subject_id`), get, `GET /{id}/status` (pending/processed), soft delete |
| RAG query | `/api/v1/rag/query` | Embed a question and retrieve the most relevant chunks (cosine), scoped to the user's documents |
| AI | `/api/v1/ai/ask` | RAG-augmented answer: retrieves context, then generates via the LLM gateway |
| AI providers | `/api/v1/ai/health` · `PATCH /api/v1/ai/providers/{name}` | Provider status (configured/enabled/active/circuit) and runtime enable/disable (admin) |

### AI generation (LLM gateway)

`POST /api/v1/ai/ask` retrieves the user's most relevant chunks and asks an LLM
to answer using that context. The **LLM gateway** tries providers in a fallback
chain — **Claude → OpenAI → Gemini → Ollama (local)** — each guarded by a retry
policy and a circuit breaker: a provider that is unavailable (no API key) or
failing is skipped and the next one is tried. Configure keys/models via
`ANTHROPIC_*`, `OPENAI_*`, `GEMINI_*` and `OLLAMA_CHAT_MODEL` in `.env` (Ollama
needs no key and is the final fallback).

Two things keep this endpoint from cascading into the rest of the API under
load: the circuit breaker's state lives in **Redis** (`LLM_CIRCUIT_*`), not
process memory, so every API/worker process shares one view of "is this
provider down" instead of each guessing independently; and outbound calls are
capped by a process-wide semaphore (`LLM_MAX_CONCURRENCY`, default 5). The
request also doesn't hold a pooled DB connection during the LLM call itself
(only during the short retrieval phase before it) — the fallback chain can run
for minutes (multiple providers × retries × `LLM_TIMEOUT_SECONDS`), and a
held connection for that long would starve every other route's DB pool.

Providers can be inspected and toggled at runtime: `GET /api/v1/ai/health`
reports each provider's status, and `PATCH /api/v1/ai/providers/{name}`
(admin) enables/disables one. Two invariants are enforced: Ollama (the offline
fallback) can never be disabled, and at least one provider besides Ollama must
stay active. The on/off state lives in the **`ai_provider` table** (the durable
source of truth) and every toggle is written to the audit trail. **API keys are
deliberately NOT stored in the database** — they stay in the environment
(12-factor); encrypting them in the DB would only move the secret problem to
wherever the encryption key lives.

### Document ingestion (RAG)

Uploading a document (`POST /api/v1/documents`, multipart: `file`, `subject_id`,
`title`) stores it in MinIO and enqueues a Celery task. The worker then parses
it to markdown (txt/md/pdf/docx/pptx), chunks it, generates embeddings with **bge-m3**
(Ollama, 1024-dim) and indexes the chunks in pgvector for cosine search.

The task is idempotent: a redelivered or duplicate ingestion trigger for a
document that's already `PROCESSING` or `INDEXED` is a no-op instead of
re-downloading, re-parsing and re-embedding from scratch. Celery acks tasks
late (`task_acks_late`, prefetch 1), so a worker crash mid-task redelivers it
rather than losing it, relying on that same no-op guard for safety.

Pull the embedding model once after starting the stack:

```bash
docker compose exec ollama ollama pull bge-m3
```

Each resource supports `POST` (create), `GET` (list, with `limit`/`offset`),
`GET /{id}`, `PATCH /{id}` and `DELETE /{id}`.

Academic items carry a free-form `content` (JSONB) and a structured `metadata`
(JSONB) with the shape: `starts_at`, `ends_at`, `is_graded`, `weight`,
`is_individual`, `estimated_duration` (plus optional `uuid` / `academic_item_id`).

## CORS & single entrypoint

The architecture treats **Traefik as the single entrypoint**, so CORS is a
development-only concern:

- **Development:** the React app (Vite, `http://localhost:5173`) and the API are
  different origins, so a `CORSMiddleware` is enabled with the origins in
  `ALLOWED_ORIGINS` and `allow_credentials=True` (never `*`, because auth uses
  HttpOnly cookies).
- **Production:** everything is served behind Traefik on a single domain
  (`https://teacher-ai.com`, with `/api` routed to FastAPI). Same origin means
  **no CORS at all** — the middleware is not added when `APP_ENV != development`.

The browser sends the HttpOnly auth cookies automatically; there is no
`Authorization: Bearer` header and no token in `localStorage`.

## Rate limiting

Two independent layers protect the API from abuse:

1. **Per-account login lockout** (`LoginRateLimiter`, Redis) — after
   `LOGIN_RATE_LIMIT_MAX_ATTEMPTS` failed logins the account is blocked for a
   window. Defends a targeted credential-stuffing attempt on one account.
2. **Per-IP request limiting** (`slowapi` + Redis, `app/api/rate_limit.py`) — a
   global default applies to **every** route, with stricter limits on sensitive
   ones. Defends the whole API from a single client flooding it (DoS). Counters
   live in Redis (db 3), so the limit holds across API replicas, not per-process.

| Scope | Default | Env var |
|-------|---------|---------|
| Every route | `120/minute` | `RATE_LIMIT_DEFAULT` |
| Auth (`/auth/login`, `/auth/register`) | `10/minute` | `RATE_LIMIT_AUTH` |
| Expensive (`/ai/ask`, `POST /plans`, upload) | `20/minute` | `RATE_LIMIT_EXPENSIVE` |

Over-limit requests get `429` with `X-RateLimit-*`/`Retry-After` headers. The
real client IP is taken from Traefik's `X-Forwarded-For`. Liveness/readiness
probes are exempt. Toggle the whole layer with `RATE_LIMIT_ENABLED` (off under
test). Covered by `app/api/tests/test_rate_limit.py`.

## Security hardening

Beyond auth and rate limiting, the app defends the OWASP-relevant surfaces:

- **Security headers** (`app/api/security_headers.py`) — every response carries
  `Content-Security-Policy` (locked to `default-src 'none'` for the JSON API, a
  looser policy only for `/docs`), `X-Frame-Options: DENY` (clickjacking),
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `Permissions-Policy`, and `Strict-Transport-Security` in production (HTTPS).
- **Safe uploads** (`app/modules/documents/domain/upload_validation.py`) — never
  trust the client. Before storing, we validate the **extension** (allow-list),
  the declared **MIME**, and the real **magic bytes** (a `virus.exe` renamed
  `notes.pdf` is rejected), and enforce a **size limit** (`MAX_UPLOAD_SIZE_MB`,
  default 100 MB) with a bounded read so a huge file can't exhaust memory before
  it's rejected (`413`). Files are only stored/parsed, never executed.
- **Prompt injection** (`app/shared/ai/prompt_safety.py`) — retrieved document
  text is attacker-controlled ("ignore all previous instructions…"). It is never
  spliced raw into a prompt: it's wrapped in `<untrusted_document_context>`
  delimiters and every AI system prompt instructs the model to treat that block
  as reference data, never as commands.
- **RAG tenant isolation** — the similarity search is **always** scoped to the
  content ids the user owns (`ChunkRepository.search_similar` refuses to run
  without a scope). One teacher can never retrieve another teacher's material.
- **SQL injection** — 100% SQLAlchemy ORM with bound parameters; no
  string-interpolated SQL anywhere (the only raw statement is a static
  `SELECT 1` readiness probe).
- **Dependency & secret scanning** — `dependabot` (weekly PRs for pip, Actions,
  Docker) plus a CI `security` job running `pip-audit` (known CVEs) and
  `gitleaks` (committed secrets), both **blocking** (a finding fails the
  build). Secrets live only in `.env` (git-ignored); only `.env.example` is
  committed.
- **CSRF** (`app/api/csrf.py`, double-submit cookie) — the auth cookies are
  HttpOnly, so a same-site attacker page can still make the browser send them.
  A non-HttpOnly `csrf_token` cookie is set alongside them; every unsafe
  request (except `/auth/login`/`/auth/register`, which precede any session)
  must mirror it into an `X-CSRF-Token` header, or gets `403`. Skipped when no
  session cookie is present at all — there's no ambient authority to protect.
- **TLS** — Traefik terminates HTTPS on `:443` with a self-signed cert
  (`make certs`) by default; swap to a real Let's Encrypt resolver by
  uncommenting the block in `docker/traefik/traefik.yml` once a domain
  exists. The old unauthenticated dashboard listener on `:8080` is disabled
  (`api.insecure: false`).
- **Non-root container** — the API/worker image runs as an unprivileged user
  (`docker/api/Dockerfile`), not root.

Covered by `test_upload_validation`, `test_prompt_safety`,
`test_search_isolation` and `test_security_headers`.

## Load / performance testing

`perf/` holds a Locust load test for the **non-AI** paths (HTTP + Postgres +
Redis + auth + CRUD) — free to run repeatedly. The AI paths are excluded on
purpose (their ceiling is the LLM provider, not this service). Run against a live
stack with `perf/run.sh` (`USERS`/`RATE`/`TIME` configurable). A captured
baseline and the capacity analysis are in `perf/RESULTS.md`.

## Postman

Import `postman/ProfPlan.postman_collection.json` (and the
`postman/ProfPlan.local.postman_environment.json` environment) into Postman to
try every endpoint. Requests send a `Host: api.localhost` header so they reach
the API through Traefik, and Postman keeps the auth cookies between calls.

## Tests

Tests run with pytest through Docker (no local Python required).

**Unit tests** (fast, no infrastructure — use in-memory fakes):

```bash
./scripts/test.sh            # all unit tests
./scripts/test.sh -q -k auth # filter by keyword
```

`core/security` (Argon2id + JWT) and `AuthService` (login, refresh rotation,
reuse detection, logout, rate limiting) are covered.

**Integration tests** (real Postgres + Redis, throwaway `*_test` database and
Redis db 15, on the stack network):

```bash
./scripts/test-integration.sh
```

These exercise the full HTTP flow with httpx against a real database:

- **auth** — login/cookies, token rotation and reuse rejection, rate limiting
  (429), audit log persisted in Postgres.
- **domain resources** — full CRUD for subjects, plans, modules, academic items
  (JSON content/metadata + soft delete) and category catalogs, plus ownership
  isolation and validation errors (422).
- **AI providers** — `GET /ai/health` fallback chain, and provider toggle guards
  (Ollama can't be disabled → 409, unknown → 404, non-admin → 403).
- **plan creation** — the CI-safe branch (plain plan when generation is disabled)
  and document-selection validation (unowned document → 404).

They live under `tests/integration/` and are marked `@pytest.mark.integration`
(the unit run excludes them).

**Coverage**: `./scripts/coverage.sh` runs the unit suite with a coverage report.

**Pre-commit** (optional): `pipx install pre-commit && pre-commit install` runs
Ruff lint + format on every commit (see `.pre-commit-config.yaml`).

Common tasks are also wrapped in a `Makefile` (`make up`, `make test`,
`make test-integration`, `make coverage`, `make migrate`, `make pull-model`, …).

## Contribution standards (Grupo Central)

The entire project must be written in **English** (code, comments, commit
messages, docs).

### Branches

Lowercase, kebab-case: `<type>-<task-description>`

| Type | Use |
|------|-----|
| `docs` | Documentation changes |
| `feat` | New feature |
| `fix` | Bug fix |
| `perf` | Performance improvements |
| `refactor` | Refactoring without behavior change |
| `style` | Style adjustments (formatting, css) |
| `test` | Creating or fixing tests |

Example: `feat-create-payment-flow`

### Commits

`<type>/<change-description>` — imperative mood, lowercase first letter, no
trailing period. Types: `docs/`, `feat/`, `fix/`, `perf/`, `refactor/`,
`style/`, `test/`.

Example: `feat/create-payment-endpoint`

### Pull Requests

`<Type>: <change description> - #<azure-task-code>` — capitalized type, always
include the Azure task code.

Example: `Feat: Create recurring payment flow - #456`

When opening a PR:

1. Resolve conflicts, if any.
2. Link the Work Items to the related User Stories in Azure.
3. Post the PR link in Slack, in the `#revisão-pr` channel.
