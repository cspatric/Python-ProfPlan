"""Celery worker bootstrap."""

import os

from celery import Celery
from celery.signals import worker_process_init

celery_app = Celery(
    "profplan",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2"),
    include=["app.infrastructure.celery.tasks.ingest"],
)


@worker_process_init.connect
def _setup_worker_tracing(**_: object) -> None:
    """Enable tracing inside each worker process (opt-in via OTEL_ENABLED)."""
    from app.infrastructure.telemetry.traces import setup_tracing

    setup_tracing("profplan-worker")
