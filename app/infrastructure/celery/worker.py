"""Celery worker bootstrap."""

import os

from celery import Celery

celery_app = Celery(
    "profplan",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2"),
    include=["app.infrastructure.celery.tasks.ingest"],
)
