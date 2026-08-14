#!/usr/bin/env python
"""Look at, and replay, the tasks that were given up on.

    python scripts/dead_letter.py list [--limit 20]
    python scripts/dead_letter.py replay [--task documents.ingest] [--yes]

Run it inside the API or worker container, where the broker is reachable:

    docker compose exec api python scripts/dead_letter.py list

`list` reads without consuming, so it is safe to run whenever. `replay` takes
the entries out and re-queues them, which is the whole reason the arguments
are kept: recovering a batch of failures should be a command, not an
afternoon of reconstructing ids from a log.
"""

import argparse
import sys
from datetime import UTC, datetime

from app.infrastructure.celery import dead_letter

# Only tasks whose arguments are safe and meaningful to replay. An email is
# not here on purpose: its body was never stored (a reset token has no
# business sitting in a failure list), so replaying one would send an empty
# message.
REPLAYABLE = {
    "documents.ingest": ("app.infrastructure.celery.tasks.ingest", "ingest_document"),
    "generation.run_item": ("app.infrastructure.celery.tasks.generate", "run_item"),
    "plans.generate": ("app.infrastructure.celery.tasks.generate", "generate_plan"),
}


def _when(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def command_list(limit: int) -> int:
    entries = dead_letter.entries(limit)
    total = dead_letter.depth()
    if not entries:
        print("nothing has been given up on")
        return 0

    print(f"{total} dead letter(s), showing {len(entries)}, newest first\n")
    for entry in entries:
        print(f"  {_when(entry['failed_at'])}  {entry['task']}")
        print(f"    args:    {', '.join(entry['args'])}")
        print(f"    retries: {entry['retries']}")
        print(f"    error:   {entry['error'][:160]}")
        print()
    return 0


def command_replay(task_filter: str | None, assume_yes: bool) -> int:
    # Everything is taken out first: replaying from a list that is still being
    # read is how one failure gets requeued twice.
    entries = dead_letter.drain()
    if not entries:
        print("nothing to replay")
        return 0

    chosen = [e for e in entries if task_filter is None or e["task"] == task_filter]
    skipped = [e for e in entries if e not in chosen]

    print(f"replaying {len(chosen)} of {len(entries)} dead letter(s)")
    if not assume_yes:
        reply = input("continue? [y/N] ")
        if reply.strip().lower() != "y":
            # Put them back: an aborted replay must not be a deletion.
            for entry in reversed(entries):
                dead_letter.record(
                    task=entry["task"],
                    args=entry["args"],
                    error=entry["error"],
                    retries=entry["retries"],
                )
            print("aborted, nothing was lost")
            return 1

    replayed = failed = 0
    for entry in chosen:
        target = REPLAYABLE.get(entry["task"])
        if target is None:
            print(f"  skipping {entry['task']}: not replayable")
            failed += 1
            continue
        module_name, attribute = target
        module = __import__(module_name, fromlist=[attribute])
        getattr(module, attribute).delay(*entry["args"])
        replayed += 1
        print(f"  requeued {entry['task']} {entry['args']}")

    # Whatever was filtered out, or could not be replayed, goes back on the
    # list. Draining is not the same as discarding.
    for entry in reversed(skipped):
        dead_letter.record(
            task=entry["task"],
            args=entry["args"],
            error=entry["error"],
            retries=entry["retries"],
        )

    print(f"\nrequeued {replayed}, left alone {failed + len(skipped)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="show the dead letters without touching them")
    listing.add_argument("--limit", type=int, default=20)

    replay = sub.add_parser("replay", help="re-queue them")
    replay.add_argument("--task", help="only this task name")
    replay.add_argument("--yes", action="store_true", help="do not ask")

    args = parser.parse_args()
    if args.command == "list":
        return command_list(args.limit)
    return command_replay(args.task, args.yes)


if __name__ == "__main__":
    sys.exit(main())
