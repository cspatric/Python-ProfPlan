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
| traefik | `traefik:v3.3` | Edge router / reverse proxy | 80, 8080 (dashboard) |
| api | built (`docker/api`) | FastAPI application | via traefik (`api.localhost`) |
| worker | same image as api | Celery worker (background jobs) | — |
| flower | same image as api | Celery monitoring dashboard | 5555 |
| postgres | `pgvector/pgvector:pg17` | Database + pgvector (not exposed) | — |
| redis | `redis:8-alpine` | Cache + Celery broker/backend | — |
| minio | `minio/minio` | S3-compatible object storage | 9000, 9001 (console) |
| prometheus | `prom/prometheus` | Metrics | 9090 |
| grafana | `grafana/grafana` | Dashboards | 3000 |
| loki | `grafana/loki` | Log aggregation | 3100 |
| otel-collector | `otel/opentelemetry-collector-contrib` | Telemetry pipeline | 4317, 4318 |
| adminer | `adminer` | DB UI (development only) | 8081 |

Two networks: `frontend` (edge, Traefik ↔ API) and `backend` (internal —
PostgreSQL is never exposed to the host). Named volumes persist Postgres, Redis,
MinIO and Grafana data.

> This repository is **backend-only**. The React frontend lives in a separate
> repository and is intentionally not part of this stack.

## Running the environment

```bash
cp .env.example .env   # fill in the values
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
| API (FastAPI) | http://api.localhost/health | Via Traefik. Add `127.0.0.1 api.localhost` to your hosts file, or send `Host: api.localhost` header |
| Traefik dashboard | http://localhost:8080/dashboard/ | Router/service overview |
| Flower (Celery) | http://localhost:5555 | Tasks, queues, workers |
| Grafana | http://localhost:3000 | Default login `admin` / `admin` (Prometheus + Loki datasources pre-provisioned) |
| Prometheus | http://localhost:9090 | Metrics |
| MinIO console | http://localhost:9001 | Login with `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` from `.env` |
| MinIO API (S3) | http://localhost:9000 | S3-compatible endpoint |
| Adminer | http://localhost:8081 | DB UI — server `postgres`, credentials from `.env` |
| Loki | http://localhost:3100 | Log API (`/ready`, `/loki/api/...`) |
| OTel Collector | grpc `localhost:4317` / http `localhost:4318` | OTLP ingest |
| PostgreSQL | _not exposed to the host_ | Reachable only inside the `backend` network |
| Redis | _not exposed to the host_ | Reachable only inside the `backend` network |

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

These exercise the full HTTP flow with httpx: login/cookies, token rotation and
reuse rejection, rate limiting (429) and the audit log persisted in Postgres.
Live under `tests/integration/` and are marked `@pytest.mark.integration` (the
unit run excludes them).

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
