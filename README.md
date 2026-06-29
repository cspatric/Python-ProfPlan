# Python-ProfPlan

ProfPlan backend — AI/RAG-powered teaching plans platform.

Modular architecture (DDD) with FastAPI, PostgreSQL/pgvector, Redis, Celery,
MinIO and an observability stack (Prometheus, Loki, Grafana, Traefik).

## Running the environment

```bash
cp .env.example .env   # fill in the values
docker compose up --build
```
