"""Application metrics beyond the HTTP defaults, plus the probe that fills them.

``prometheus-fastapi-instrumentator`` already exports request rate, latency and
status codes. The three things it cannot see are exactly the three worth being
paged about, so they are defined here on the default registry and therefore
appear on the same ``/metrics`` endpoint:

* whether our dependencies answer (``/ready`` tells you this, but only when
  someone calls it, and Prometheus scrapes ``/metrics``, not ``/ready``);
* how many messages are waiting in the Celery queue;
* how the LLM fallback chain is behaving, per provider.

The dependency and queue gauges are filled by a background probe started in the
app's lifespan. It is deliberately cheap (a ``SELECT 1``, a ``PING`` and an
``LLEN``) and its failures never propagate: a probe that cannot reach a
dependency records a zero, which is the whole point.
"""

import asyncio
import contextlib
import logging

from prometheus_client import Counter, Gauge, Histogram
from redis.asyncio import from_url
from sqlalchemy import text

from app.core.config import get_settings
from app.infrastructure.celery.dead_letter import DEAD_LETTER_KEY

logger = logging.getLogger("app.metrics")

# multiprocess_mode matters as soon as UVICORN_WORKERS > 1: every worker runs
# its own probe, so the same gauge has one value per process. "livemostrecent"
# reports the newest sample from a process that is still alive, which is the
# only reading that answers "is the database up right now". "max" would hide an
# outage the moment one worker still believed things were fine.
DEPENDENCY_UP = Gauge(
    "profplan_dependency_up",
    "1 when the dependency answered its last probe, 0 when it did not.",
    ["dependency"],
    multiprocess_mode="livemostrecent",
)

# A dead letter is work that was accepted and then dropped: a document nobody
# can search, a plan that never filled in, a reset email that never arrived.
# Nothing else in the stack reports it, because from the queue's point of view
# those tasks are finished.
DEAD_LETTER_DEPTH = Gauge(
    "profplan_dead_letter_depth",
    "Tasks that exhausted their retries and are waiting to be looked at.",
    multiprocess_mode="livemostrecent",
)

CELERY_QUEUE_DEPTH = Gauge(
    "profplan_celery_queue_depth",
    "Messages waiting to be picked up by a Celery worker.",
    ["queue"],
    multiprocess_mode="livemostrecent",
)

LLM_REQUESTS = Counter(
    "profplan_llm_requests_total",
    "LLM gateway attempts, by provider and outcome.",
    ["provider", "outcome"],
)

# The SLI behind "a plan is drafted while the teacher is still watching"
# (docs/observability/SLO.md). Measured from the moment the plan is created to
# the moment its roadmap exists, which is the wait a teacher actually
# experiences; timing the LLM call alone would leave out the queue, and the
# queue is where the wait grows under load.
#
# The buckets are placed around the objective (120s) rather than spread evenly,
# because the only question this has to answer precisely is "what fraction
# landed under two minutes".
PLAN_DRAFT_SECONDS = Histogram(
    "profplan_plan_draft_seconds",
    "Time from creating a plan to its roadmap existing.",
    buckets=(5, 15, 30, 60, 90, 120, 180, 300, 600),
)

PLAN_DRAFTS = Counter(
    "profplan_plan_drafts_total",
    "Plan drafting attempts, by outcome.",
    ["outcome"],
)

# --------------------------------------------------------------------------- #
# What the AI costs.
#
# The question these exist to answer is "what did that plan cost", and the
# expensive part of the answer is *which model* answered: the same prompt is
# half a cent on the local model and thirty on Opus, and the fallback chain
# means the application does not choose. Provider alone cannot say that, so
# everything here carries the model as well.
# --------------------------------------------------------------------------- #
LLM_TOKENS = Counter(
    "profplan_llm_tokens_total",
    "Tokens reported by the provider, by provider, model and direction.",
    ["provider", "model", "direction"],
)

LLM_COST_USD = Counter(
    "profplan_llm_cost_usd_total",
    "Cost in USD at list price, by provider and model.",
    ["provider", "model"],
)

# Separate from the request latency histogram: an LLM call is seconds to
# minutes, so the default web buckets would put every call in +Inf and answer
# nothing. These buckets are placed where the interesting differences are, a
# fast local answer, a normal one, and the ones that are about to time out.
LLM_LATENCY_SECONDS = Histogram(
    "profplan_llm_latency_seconds",
    "Time to a successful completion, by provider and model.",
    ["provider", "model"],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
)

# Tokens counted with no price to apply to them. Zero is the healthy value;
# anything else means somebody configured a model that nobody priced, and the
# cost total silently stopped being the whole bill.
LLM_UNPRICED = Counter(
    "profplan_llm_unpriced_calls_total",
    "Completions whose model has no price in the table.",
    ["provider", "model"],
)

LLM_ALL_PROVIDERS_FAILED = Counter(
    "profplan_llm_all_providers_failed_total",
    "Generations where every provider in the fallback chain failed.",
)


async def _probe_database() -> None:
    # Imported here, not at module scope: the worker imports this module for the
    # LLM counters and has no business building the API's pooled engine.
    from app.infrastructure.database.session import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        DEPENDENCY_UP.labels(dependency="database").set(1)
    except Exception as exc:  # noqa: BLE001 — a failed probe is a measurement
        DEPENDENCY_UP.labels(dependency="database").set(0)
        logger.warning("dependency probe failed: database (%s)", exc)


async def _probe_redis() -> None:
    from app.infrastructure.redis.client import redis_client

    try:
        await redis_client.ping()
        DEPENDENCY_UP.labels(dependency="redis").set(1)
    except Exception as exc:  # noqa: BLE001
        DEPENDENCY_UP.labels(dependency="redis").set(0)
        logger.warning("dependency probe failed: redis (%s)", exc)


async def _probe_queue_depth(broker, queues: list[str]) -> None:
    """Queue depth is the length of the broker list Celery pushes onto."""
    for queue in queues:
        try:
            depth = await broker.llen(queue)
            CELERY_QUEUE_DEPTH.labels(queue=queue).set(depth)
        except Exception as exc:  # noqa: BLE001
            logger.warning("queue depth probe failed: %s (%s)", queue, exc)


async def _probe_dead_letter(broker) -> None:
    """Report how much work has been given up on."""
    try:
        DEAD_LETTER_DEPTH.set(await broker.llen(DEAD_LETTER_KEY))
    except Exception:  # noqa: BLE001 — a probe must never take the app down
        logger.debug("dead letter probe failed", exc_info=True)


async def probe_once(broker, queues: list[str]) -> None:
    """One round of every probe. Never raises."""
    await _probe_database()
    await _probe_redis()
    await _probe_queue_depth(broker, queues)
    await _probe_dead_letter(broker)


async def _probe_loop() -> None:
    settings = get_settings()
    queues = [q.strip() for q in settings.celery_queues.split(",") if q.strip()]
    broker = from_url(settings.celery_broker_url, decode_responses=True)
    try:
        while True:
            await probe_once(broker, queues)
            await asyncio.sleep(settings.metrics_probe_interval_seconds)
    finally:
        await broker.aclose()


def start_metrics_probe() -> asyncio.Task | None:
    """Start the background probe, or return None when it is disabled."""
    if not get_settings().metrics_probe_enabled:
        return None
    return asyncio.create_task(_probe_loop(), name="metrics-probe")


async def stop_metrics_probe(task: asyncio.Task | None) -> None:
    """Cancel the probe and wait for it to unwind (shutdown path)."""
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
