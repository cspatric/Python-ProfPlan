"""Where a task goes when it has run out of retries.

Celery with a Redis broker has no dead letter queue of its own: a task that
exhausts its retries raises, the exception is logged, and the message is gone.
For this system that meant a document nobody could reindex and a plan whose
drafting nobody could resume, with the only trace being a line in a log that
rotates.

So a failure that has given up is written here: what it was, what it was
called with, and why it stopped. Two things that costs:

* **It can be looked at.** `scripts/dead_letter.py list` answers "what has
  failed since Friday" without reading logs.
* **It can be replayed.** The arguments are kept, so requeueing is
  mechanical rather than a reconstruction from a stack trace.

The list is capped. An unbounded failure log is a second outage waiting behind
the first one, and the newest failures are the ones worth keeping.
"""

import json
import logging
import time
from typing import Any

from redis import Redis

from app.core.config import get_settings

logger = logging.getLogger("app.dead_letter")

#: One Redis list, on the broker's own database: a dead letter belongs next to
#: the queue it fell out of, not in the cache.
DEAD_LETTER_KEY = "profplan:dead-letter"

#: Kept newest first, older ones dropped past this. Enough to cover a bad
#: weekend, far short of anything that could fill the instance.
MAX_ENTRIES = 1000


def record(
    *,
    task: str,
    args: tuple[Any, ...] | list[Any],
    error: str,
    retries: int,
    redis: Redis | None = None,
) -> None:
    """Write a failed task to the dead letter list. Never raises.

    Deliberately swallowing its own errors: this is called from the failure
    path of a task that has already failed, and a broker that is down must not
    turn one lost task into a crashed worker.
    """
    settings = get_settings()
    client = redis or Redis.from_url(settings.celery_broker_url, decode_responses=True)
    entry = {
        "task": task,
        "args": [str(a) for a in args],
        "error": error[:2000],
        "retries": retries,
        "failed_at": time.time(),
    }
    try:
        pipe = client.pipeline()
        pipe.lpush(DEAD_LETTER_KEY, json.dumps(entry))
        pipe.ltrim(DEAD_LETTER_KEY, 0, MAX_ENTRIES - 1)
        pipe.execute()
        logger.warning("task moved to the dead letter queue", extra={"task": task})
    except Exception:  # noqa: BLE001 — see the docstring
        logger.exception("could not record a dead letter", extra={"task": task})
    finally:
        if redis is None:
            client.close()


def entries(limit: int = 50, redis: Redis | None = None) -> list[dict[str, Any]]:
    """The most recent dead letters, newest first."""
    settings = get_settings()
    client = redis or Redis.from_url(settings.celery_broker_url, decode_responses=True)
    try:
        raw = client.lrange(DEAD_LETTER_KEY, 0, limit - 1)
    finally:
        if redis is None:
            client.close()
    return [json.loads(item) for item in raw]


def depth(redis: Redis | None = None) -> int:
    """How many failures are waiting to be looked at."""
    settings = get_settings()
    client = redis or Redis.from_url(settings.celery_broker_url, decode_responses=True)
    try:
        return int(client.llen(DEAD_LETTER_KEY))
    finally:
        if redis is None:
            client.close()


def drain(redis: Redis | None = None) -> list[dict[str, Any]]:
    """Take everything out, so a replay cannot run the same entry twice."""
    settings = get_settings()
    client = redis or Redis.from_url(settings.celery_broker_url, decode_responses=True)
    try:
        pipe = client.pipeline()
        pipe.lrange(DEAD_LETTER_KEY, 0, -1)
        pipe.delete(DEAD_LETTER_KEY)
        raw, _ = pipe.execute()
    finally:
        if redis is None:
            client.close()
    return [json.loads(item) for item in raw]
