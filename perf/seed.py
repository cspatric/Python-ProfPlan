"""Seed a realistic dataset for the load test, then print the session pool.

Runs *inside the api container* (``docker compose exec -T api python - < seed.py``)
because that is where the DB credentials, network access and drivers already
live. It prints a JSON array of cookie dicts on stdout — run.sh captures that
into ``perf/results/.pool.json`` and locustfile.py loads it.

Why seed at all? Two measurement bugs it removes:

1. ``GET /plans`` used to return ``[]`` (2 bytes). Plans can only be created
   through the AI planner (``POST /plans``), which the load test refuses to
   call, so nothing ever created them — 22% of the traffic mix was measuring an
   empty query. Inserting plan rows straight into the table gives the endpoint
   real work without spending a token.
2. Tables filled up *during* the ramp, so early steps ran against near-empty
   tables and late steps against a full page. That made throughput
   non-monotonic and mixed "data growth" into what should measure concurrency.
   Seeding to the steady state (a full page, the list endpoints cap at 50)
   makes every step comparable.

Old load-test data is dropped first so runs stay reproducible and the dev DB
does not grow forever. Only rows owned by ``load-%@load.example.com`` accounts
are touched; the cascade removes their subjects/plans.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date, timedelta

import asyncpg
import httpx

from app.core.config import get_settings

ACCOUNTS = int(os.getenv("ACCOUNTS", "20"))
SUBJECTS_PER_ACCOUNT = int(os.getenv("SUBJECTS_PER_ACCOUNT", "60"))
PLANS_PER_ACCOUNT = int(os.getenv("PLANS_PER_ACCOUNT", "60"))
BASE_URL = os.getenv("SEED_BASE_URL", "http://localhost:8000")
API = "/api/v1"


def _dsn() -> str:
    # SQLAlchemy's async URL -> plain libpq DSN that asyncpg understands.
    return str(get_settings().database_url).replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _ip(n: int) -> str:
    """Distinct IP per registration so the per-IP auth limiter (10/min) allows it."""
    return f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


async def main() -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        # Reproducible baseline: drop whatever a previous run left behind.
        deleted = await conn.execute(
            "DELETE FROM users WHERE email LIKE 'load-%@load.example.com'"
        )
        print(f"cleanup: {deleted}", file=sys.stderr)

        pool: list[dict[str, str]] = []
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
            for i in range(ACCOUNTS):
                email = f"load-{uuid.uuid4().hex[:12]}@load.example.com"
                resp = await client.post(
                    f"{API}/auth/register",
                    json={"name": "Load", "email": email, "password": "Senha@123"},
                    headers={"X-Forwarded-For": _ip(i + 1)},
                )
                if resp.status_code not in (200, 201):
                    raise RuntimeError(
                        f"register failed: {resp.status_code} {resp.text[:200]}"
                    )
                pool.append(dict(resp.cookies))

                user_id = await conn.fetchval(
                    "SELECT uuid FROM users WHERE email = $1", email
                )

                subject_ids = [uuid.uuid4() for _ in range(SUBJECTS_PER_ACCOUNT)]
                await conn.executemany(
                    "INSERT INTO subjects (uuid, user_id, name, knowledge_area) "
                    "VALUES ($1, $2, $3, $4)",
                    [
                        (sid, user_id, f"Subject {n:03d}", "Exact sciences")
                        for n, sid in enumerate(subject_ids)
                    ],
                )
                start = date(2026, 3, 1)
                await conn.executemany(
                    "INSERT INTO plans (uuid, user_id, subject_id, starts_at, ends_at, "
                    "class_duration, class_per_week, total_weight) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                    [
                        (
                            uuid.uuid4(),
                            user_id,
                            subject_ids[n % len(subject_ids)],
                            start,
                            start + timedelta(days=120),
                            50,
                            2,
                            10.0,
                        )
                        for n in range(PLANS_PER_ACCOUNT)
                    ],
                )
        print(
            f"seeded {ACCOUNTS} accounts x {SUBJECTS_PER_ACCOUNT} subjects "
            f"/ {PLANS_PER_ACCOUNT} plans",
            file=sys.stderr,
        )
        # stdout carries ONLY the pool JSON — run.sh redirects it to a file.
        print(json.dumps(pool))
    finally:
        await conn.close()


asyncio.run(main())
