"""Celery worker bootstrap."""

import os

from celery import Celery
from celery.signals import worker_process_init

celery_app = Celery(
    "profplan",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2"),
    include=[
        "app.infrastructure.celery.tasks.ingest",
        "app.infrastructure.celery.tasks.generate",
    ],
)
celery_app.conf.update(
    # Ack only after the task returns, so a worker crash mid-task redelivers
    # it instead of silently losing it (relies on tasks being idempotent —
    # see IngestionService.ingest's PROCESSING/INDEXED no-op guard).
    task_acks_late=True,
    # Don't let one worker hoard several unacked tasks while others sit idle.
    worker_prefetch_multiplier=1,
)


@worker_process_init.connect
def _setup_worker_tracing(**_: object) -> None:
    """Enable tracing inside each worker process (opt-in via OTEL_ENABLED)."""
    from app.infrastructure.telemetry.traces import setup_tracing

    setup_tracing("profplan-worker")


# Import every model module so SQLAlchemy's mapper metadata is complete in the
# worker process (tasks touch cross-module foreign keys, e.g. academic_items ->
# users). Without this, mapper configuration raises NoReferencedTableError.
from app.modules.academic_item_categories.infrastructure import (  # noqa: E402, F401
    models as _category_models,
)
from app.modules.academic_items.infrastructure import (  # noqa: E402, F401
    models as _academic_item_models,
)
from app.modules.audit.infrastructure import models as _audit_models  # noqa: E402, F401
from app.modules.auth.infrastructure import models as _auth_models  # noqa: E402, F401
from app.modules.catalogs.infrastructure import (  # noqa: E402, F401
    models as _catalog_models,
)
from app.modules.documents.infrastructure import (  # noqa: E402, F401
    models as _document_models,
)
from app.modules.generation.infrastructure import (  # noqa: E402, F401
    models as _generation_models,
)
from app.modules.plan_modules.infrastructure import (  # noqa: E402, F401
    models as _module_models,
)
from app.modules.rag.infrastructure import models as _rag_models  # noqa: E402, F401
from app.modules.subjects.infrastructure import (  # noqa: E402, F401
    models as _subject_models,
)
from app.modules.teaching_plans.infrastructure import (  # noqa: E402, F401
    models as _plan_models,
)
from app.modules.users.infrastructure import models as _user_models  # noqa: E402, F401
