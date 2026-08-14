"""Unit tests for the dead letter queue, against a fake Redis.

What these pin down is the promise: work that was accepted and then given up
on leaves a trace carrying enough to replay it, and recording that trace can
never itself break the worker.
"""

import json

from app.infrastructure.celery import dead_letter


class FakeRedis:
    """Enough of a Redis list to exercise the calls made here."""

    def __init__(self, *, broken: bool = False) -> None:
        self.items: list[str] = []
        self.broken = broken
        self.closed = False

    # --- pipeline ---------------------------------------------------------
    def pipeline(self):
        return FakePipeline(self)

    def lrange(self, _key: str, start: int, end: int) -> list[str]:
        return self.items[start : None if end == -1 else end + 1]

    def llen(self, _key: str) -> int:
        return len(self.items)

    def delete(self, _key: str) -> None:
        self.items = []

    def close(self) -> None:
        self.closed = True


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple] = []

    def lpush(self, key: str, value: str) -> "FakePipeline":
        self._ops.append(("lpush", value))
        return self

    def ltrim(self, key: str, start: int, end: int) -> "FakePipeline":
        self._ops.append(("ltrim", end))
        return self

    def lrange(self, key: str, start: int, end: int) -> "FakePipeline":
        self._ops.append(("lrange", None))
        return self

    def delete(self, key: str) -> "FakePipeline":
        self._ops.append(("delete", None))
        return self

    def execute(self) -> list:
        if self._redis.broken:
            raise ConnectionError("broker is down")
        results = []
        for op, value in self._ops:
            if op == "lpush":
                self._redis.items.insert(0, value)
                results.append(len(self._redis.items))
            elif op == "ltrim":
                self._redis.items = self._redis.items[: value + 1]
                results.append(True)
            elif op == "lrange":
                results.append(list(self._redis.items))
            elif op == "delete":
                self._redis.items = []
                results.append(1)
        return results


def test_a_failure_keeps_what_it_needs_to_be_replayed() -> None:
    redis = FakeRedis()

    dead_letter.record(
        task="documents.ingest",
        args=("abc-123",),
        error="the embedder took too long",
        retries=3,
        redis=redis,
    )

    entry = json.loads(redis.items[0])
    # The arguments are the point: without them a replay is a reconstruction.
    assert entry["args"] == ["abc-123"]
    assert entry["task"] == "documents.ingest"
    assert entry["retries"] == 3
    assert "embedder" in entry["error"]
    assert entry["failed_at"] > 0


def test_recording_never_breaks_the_worker() -> None:
    """This runs on the failure path of something that already failed.

    A broker that is down must not turn one lost task into a crashed worker.
    """
    redis = FakeRedis(broken=True)

    dead_letter.record(
        task="documents.ingest", args=("abc",), error="x", retries=1, redis=redis
    )  # must not raise


def test_the_list_is_capped() -> None:
    redis = FakeRedis()

    for i in range(dead_letter.MAX_ENTRIES + 25):
        dead_letter.record(task="t", args=(str(i),), error="e", retries=0, redis=redis)

    # An unbounded failure log is a second outage behind the first one.
    assert len(redis.items) == dead_letter.MAX_ENTRIES
    # And what survives is the newest.
    assert json.loads(redis.items[0])["args"] == [str(dead_letter.MAX_ENTRIES + 24)]


def test_newest_first() -> None:
    redis = FakeRedis()

    dead_letter.record(task="t", args=("old",), error="e", retries=0, redis=redis)
    dead_letter.record(task="t", args=("new",), error="e", retries=0, redis=redis)

    assert [e["args"][0] for e in dead_letter.entries(10, redis=redis)] == [
        "new",
        "old",
    ]


def test_draining_empties_the_list() -> None:
    redis = FakeRedis()
    dead_letter.record(task="t", args=("a",), error="e", retries=0, redis=redis)
    dead_letter.record(task="t", args=("b",), error="e", retries=0, redis=redis)

    drained = dead_letter.drain(redis=redis)

    # Taken out in one step, so a replay cannot run the same entry twice.
    assert len(drained) == 2
    assert dead_letter.depth(redis=redis) == 0


def test_depth_counts_what_is_waiting() -> None:
    redis = FakeRedis()
    assert dead_letter.depth(redis=redis) == 0

    dead_letter.record(task="t", args=("a",), error="e", retries=0, redis=redis)

    assert dead_letter.depth(redis=redis) == 1
