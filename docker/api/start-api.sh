#!/bin/sh
# Entrypoint for the API container only. The worker and Flower override the
# image's command, so they never run this.
#
# Two things have to happen before uvicorn starts, and both exist because of
# multiple workers:
#
#   1. With --workers N, uvicorn forks N processes. Each one would keep its own
#      prometheus_client registry, so /metrics would return whichever process
#      happened to answer the scrape and every counter would appear to jump
#      around. prometheus_client's multiprocess mode fixes that by having the
#      processes write into a shared directory that the scrape then merges.
#   2. That directory holds one file per process id. Stale files from a
#      previous run would be merged into the next one, so it is wiped at boot.
set -e

WORKERS="${UVICORN_WORKERS:-1}"

if [ -n "$PROMETHEUS_MULTIPROC_DIR" ]; then
    rm -rf "${PROMETHEUS_MULTIPROC_DIR:?}"/*
    mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
elif [ "$WORKERS" -gt 1 ]; then
    echo "refusing to start: UVICORN_WORKERS=$WORKERS needs PROMETHEUS_MULTIPROC_DIR" >&2
    echo "without it /metrics reports one worker at random and the alerts lie" >&2
    exit 1
fi

# --no-access-log: RequestLoggingMiddleware is the single, richer source of
# access logs (structured JSON, with the acting user and the trace id).
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --no-access-log \
    --workers "$WORKERS"
