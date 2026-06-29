# Python-ProfPlan

ProfPlan backend — AI/RAG-powered teaching plans platform.

Modular architecture (DDD) with FastAPI, PostgreSQL/pgvector, Redis, Celery,
MinIO and an observability stack (Prometheus, Loki, Grafana, Traefik).

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
