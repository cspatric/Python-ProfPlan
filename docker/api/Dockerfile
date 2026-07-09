# syntax=docker/dockerfile:1

# Single image shared by the API and the Celery worker — only the command differs.
FROM python:3.14-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# System dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# uv (fast dependency manager)
COPY --from=ghcr.io/astral-sh/uv:0.5.29 /uv /uvx /bin/

# Resolve dependencies from the lockfile (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Application code and migrations
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

EXPOSE 8000

# --no-access-log: the app's RequestLoggingMiddleware is the single, richer
# (structured JSON, with user context) source of HTTP access logs.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
