# syntax=docker/dockerfile:1

# Single image shared by the API and the Celery worker — only the command differs.
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# System dependencies
# build-essential/curl for the build and the healthcheck; the pango, cairo and
# gdk-pixbuf libraries are WeasyPrint's text shaping and rasterising backend,
# which it loads at runtime and cannot ship itself.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential curl \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libfribidi0 \
        libcairo2 libgdk-pixbuf-2.0-0 \
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
COPY docker/api/start-api.sh /usr/local/bin/start-api
RUN chmod +x /usr/local/bin/start-api

# Run as an unprivileged user (both the API and the Celery worker use this
# image) so a future RCE in a dependency can't write outside /app or touch
# anything else in the container as root.
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# CMD, not ENTRYPOINT: the worker and Flower replace the command entirely, and
# an entrypoint would still wrap them. See docker/api/start-api.sh for why the
# API needs a script rather than a plain uvicorn line.
CMD ["start-api"]
