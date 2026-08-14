"""Celery worker bootstrap."""

import logging
import os

from celery import Celery
from celery.signals import (
    setup_logging as celery_setup_logging,
)
from celery.signals import (
    worker_process_init,
    worker_process_shutdown,
    worker_ready,
)

logger = logging.getLogger("app.worker")

celery_app = Celery(
    "profplan",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2"),
    include=[
        "app.infrastructure.celery.tasks.ingest",
        "app.infrastructure.celery.tasks.generate",
        "app.infrastructure.celery.tasks.email",
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


#: Where the worker answers a Prometheus scrape. A port rather than a file,
#: because Prometheus pulls: pushing from a worker would need a gateway, and a
#: pushgateway keeps reporting the last value of a worker that has died.
METRICS_PORT = int(os.getenv("WORKER_METRICS_PORT", "9200"))


@celery_setup_logging.connect
def _use_the_application_log_format(**_: object) -> None:
    """Stop Celery from replacing the JSON logging with its own format.

    Connecting to this signal at all is what disables Celery's configuration;
    what is done inside it is then the whole of it. Without this the worker
    printed lines like "INFO/ForkPoolWorker-6 llm call" and every structured
    field went nowhere, which is a problem here specifically: every LLM call
    the product makes happens in a task, so the per-call cost line was the one
    line that never reached Loki.
    """
    from app.core.config import get_settings
    from app.infrastructure.telemetry.logging import setup_logging

    setup_logging(get_settings().log_level)


@worker_ready.connect
def _serve_metrics(**_: object) -> None:
    """Expose the worker's metrics, merged across its child processes.

    This matters more than it looks: every LLM call the product actually makes
    happens *here*, in a task, not in the API. Before this, the cost and token
    metrics existed and nothing scraped them, which is the same as not having
    them.

    Runs in the main process, once. Celery forks its pool, so each child keeps
    its own registry; prometheus_client's multiprocess mode has them write into
    a shared directory that this endpoint merges at scrape time. Without
    PROMETHEUS_MULTIPROC_DIR the endpoint would report whichever child happened
    to answer, so it refuses to lie and serves nothing instead.
    """
    if not os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        logger.warning(
            "worker metrics are off: PROMETHEUS_MULTIPROC_DIR is not set, so "
            "per-process counters cannot be merged"
        )
        return

    from prometheus_client import CollectorRegistry, multiprocess, start_http_server

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    start_http_server(METRICS_PORT, registry=registry)
    logger.info("worker metrics on :%d", METRICS_PORT)


@worker_process_shutdown.connect
def _forget_dead_process(pid: int | None = None, **_: object) -> None:
    """Drop a finished child's gauge files.

    Counters survive on purpose, they are the totals. Gauges do not: a value
    from a process that no longer exists is a number that will never change
    again and is not true either.
    """
    if not os.getenv("PROMETHEUS_MULTIPROC_DIR") or pid is None:
        return
    from prometheus_client import multiprocess

    multiprocess.mark_process_dead(pid)


@worker_process_init.connect
def _setup_worker_process(**_: object) -> None:
    """Prepare a freshly forked pool process: tracing, and its own logging.

    The logging has to be set up again *here*, not only in the main process.
    The JSON handler writes through a QueueListener, which is a thread, and
    threads do not survive a fork: the child inherited the queue and no reader,
    so every line a task logged went into it and stayed there. The tasks are
    the entire product, so that was all of them.
    """
    from app.core.config import get_settings
    from app.infrastructure.telemetry.logging import setup_logging
    from app.infrastructure.telemetry.traces import setup_tracing

    setup_logging(get_settings().log_level)
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
