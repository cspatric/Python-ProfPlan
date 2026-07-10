"""Structured (JSON) logging setup.

Every log line is emitted as single-line JSON to stdout. The container runtime
captures stdout and Promtail ships it to Loki, where JSON keeps every field
queryable (e.g. `{container="backend-api-1"} | json | user_id="..."`) instead
of forcing regex parsing of free-form text.

Logging goes through a QueueHandler/QueueListener: request-path code (e.g.
RequestLoggingMiddleware, called on every request) only pushes onto an
in-memory queue, which is effectively instant. A dedicated background thread
drains the queue and does the actual stdout write. Without this, the blocking
write() would run directly on the asyncio event loop thread — if it ever
stalls (the container's log driver or Promtail backing up under a burst of
concurrent requests), it would stall every other request being served by that
worker, not just the one that logged.
"""

import atexit
import json
import logging
import logging.handlers
import queue
import sys

# Standard LogRecord attributes — everything else on a record (i.e. what callers
# pass via `extra=...`) is treated as a custom field and included in the JSON.
_RESERVED_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Render a log record — plus any `extra` fields — as a JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger to emit JSON to stdout via a background thread.

    Also routes uvicorn's own loggers through the same handler so that every
    line in the container output is structured JSON.
    """
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(JsonFormatter())

    # Unbounded: log lines are small and this only protects against the writer
    # thread falling behind for a moment, not sustained overload.
    log_queue: queue.SimpleQueue = queue.SimpleQueue()
    queue_handler = logging.handlers.QueueHandler(log_queue)
    listener = logging.handlers.QueueListener(
        log_queue, stream_handler, respect_handler_level=True
    )
    listener.start()
    # Flush whatever's still queued on normal interpreter shutdown.
    atexit.register(listener.stop)

    root = logging.getLogger()
    root.handlers = [queue_handler]
    root.setLevel(level.upper())

    # Drop uvicorn/gunicorn's private handlers and let their records propagate
    # to the root JSON handler instead of being printed as plain text.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
