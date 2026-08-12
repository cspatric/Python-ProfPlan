"""Load test for ProfPlan — AI-free endpoints only.

Measures the capacity of the HTTP + Postgres + Redis path (auth session, CRUD,
listing, provider health) WITHOUT calling any LLM, so it is free to run as often
as you like. The AI paths are deliberately excluded: their ceiling is the LLM
provider (Gemini quota / Ollama CPU), not this architecture — see perf/README.md.

That exclusion is *enforced*, not just documented: every request goes through
``ApiUser.api()``, which raises before opening a socket if the path is one that
spends tokens (see ``_AI_SPEND_PATHS``). A task that calls one is a bug that
fails the run rather than a surprise on the provider bill.

Two shapes:

* ``SHAPE=flat`` (default) — hold USERS constant; the classic fixed-point run.
* ``SHAPE=step``            — ramp users in steps until an SLO breaks, then stop
  and report the last healthy step. This is what answers "how many concurrent
  users does it take before the app falls over?".

Cost model note: argon2 password hashing is deliberately CPU-expensive, so
paying it once per simulated user would make *spawning* the bottleneck and hide
the read ceiling. Instead ``perf/seed.py`` registers a fixed pool of accounts up
front (and fills their tables); this file just reuses those sessions. To measure
auth throughput on purpose, give ``AuthUser`` weight via ``AUTH_WEIGHT``.
"""

from __future__ import annotations

import itertools
import json
import os
import sys
import time
import uuid

import requests
from locust import HttpUser, LoadTestShape, between, events, task

# --------------------------------------------------------------------------
# Configuration (env-driven so run.sh can stay a thin wrapper)
# --------------------------------------------------------------------------
API = "/api/v1"

ACCOUNTS = int(os.getenv("ACCOUNTS", "20"))
AUTH_WEIGHT = int(os.getenv("AUTH_WEIGHT", "0"))
UNIQUE_IPS = os.getenv("UNIQUE_IPS", "1") == "1"

# Seconds a simulated user pauses between requests. The default is deliberately
# brutal (a user hammering ~1.7 req/s) to find the infrastructure ceiling fast.
# It is NOT how a person behaves: set THINK_TIME_MIN/MAX to 5/10 to model a
# teacher clicking around, which is what answers "how many *people* fit?".
THINK_MIN = float(os.getenv("THINK_TIME_MIN", "0.05"))
THINK_MAX = float(os.getenv("THINK_TIME_MAX", "0.2"))

# --- E2E plan-generation mode (Celery pipeline, MOCK LLM only) -------------
# PLAN_WEIGHT > 0 adds users that POST /plans and poll the generation. That
# path is ONLY unlocked when BOTH are true:
#   MOCK_LLM=1      — the operator says the stack points at the mock;
#   MOCK_VERIFIED=1 — run.sh's canary PROVED it (a probe plan incremented the
#                     mock's hit counter). run.sh sets this, never by hand.
# Without both, POST /plans raises before opening a socket, like every other
# token-spending path.
MOCK_LLM = os.getenv("MOCK_LLM", "0") == "1"
MOCK_VERIFIED = os.getenv("MOCK_VERIFIED", "0") == "1"
PLAN_WEIGHT = int(os.getenv("PLAN_WEIGHT", "0"))
# Stop the run once this many requests have been served (0 = disabled).
REQUEST_TARGET = int(os.getenv("REQUEST_TARGET", "0"))

SHAPE = os.getenv("SHAPE", "flat")
STEP_START = int(os.getenv("STEP_START", "25"))
STEP_USERS = int(os.getenv("STEP_USERS", "25"))
STEP_TIME = int(os.getenv("STEP_TIME", "30"))
STEP_MAX = int(os.getenv("STEP_MAX", "500"))
STEP_SPAWN = int(os.getenv("STEP_SPAWN", "25"))
# Discard each step's first seconds: spawning plus locust's 10s sliding window
# still carry the previous step's traffic, which would smear the two together.
SETTLE_SECONDS = int(os.getenv("SETTLE_SECONDS", "20"))
# Unmeasured traffic before the first step. Without it the opening steps come
# out slower than the busier steps that follow (a cold asyncpg pool, cold
# Postgres cache and unwarmed Python), which inverts the bottom of the curve.
WARMUP_SECONDS = int(os.getenv("WARMUP_SECONDS", "60"))

# A step "passes" while both hold. p95 is the number a user actually feels; the
# failure ratio catches the pool/CPU giving up (5xx, timeouts, resets).
SLO_P95_MS = float(os.getenv("SLO_P95_MS", "1000"))
SLO_FAIL_PCT = float(os.getenv("SLO_FAIL_PCT", "1.0"))

# Paths that cost money or saturate the local GPU/CPU on a provider, not on us.
# Method-aware: GET /plans is a cheap list, POST /plans runs the planner.
_AI_SPEND_PATHS = (
    ("POST", f"{API}/ai/ask"),
    ("POST", f"{API}/rag/query"),
    ("POST", f"{API}/plans"),
    ("POST", f"{API}/documents"),
    ("POST", "/generate"),
)

_ip_counter = itertools.count(1)
_account_cycle: itertools.cycle | None = None
_pool: list[dict[str, str]] = []


def _next_ip() -> str:
    """A unique client IP per request → its own rate-limit bucket."""
    n = next(_ip_counter)
    return f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


def _is_ai_path(method: str, path: str) -> bool:
    return any(
        method.upper() == m and (path == p or path.endswith(p))
        for m, p in _AI_SPEND_PATHS
    )


# --------------------------------------------------------------------------
# Account pool — argon2 is paid once, up front, not on every user spawn
# --------------------------------------------------------------------------
POOL_FILE = os.getenv("POOL_FILE", "/mnt/locust/results/.pool.json")


def _load_pool(environment) -> None:
    """Load the sessions that perf/seed.py prepared (preferred), else register.

    seed.py also fills the tables to their steady state, so prefer it: the
    fallback measures near-empty tables and an empty GET /plans, which reads as
    more capacity than the app really has.
    """
    global _account_cycle, _pool
    if os.path.exists(POOL_FILE):
        with open(POOL_FILE) as fh:
            _pool = json.load(fh)
        print(f"Loaded {len(_pool)} seeded sessions from {POOL_FILE}.")
    else:
        host = environment.host
        print(f"WARNING: {POOL_FILE} missing — registering {ACCOUNTS} bare accounts.")
        print(
            "WARNING: tables will be near-empty; run via perf/run.sh for real numbers."
        )
        _pool = []
        for _ in range(ACCOUNTS):
            session = requests.Session()
            # NB: use a real TLD — email-validator rejects reserved ones like .local.
            email = f"load-{uuid.uuid4().hex[:12]}@load.example.com"
            resp = session.post(
                f"{host}{API}/auth/register",
                json={"name": "Load", "email": email, "password": "Senha@123"},
                headers={"X-Forwarded-For": _next_ip()},
                timeout=60,
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(
                    f"account pool setup failed: {resp.status_code} {resp.text[:200]}"
                )
            _pool.append(dict(session.cookies))
    if not _pool:
        raise RuntimeError("account pool is empty")

    # Access tokens live 15 minutes (access_token_expire_minutes). A stale
    # SEED=0 pool then 401s on every authenticated call, which shows up as ~90%
    # "failures" that look exactly like a capacity wall but are just expired
    # logins. Fail loudly here instead of publishing that as a result.
    probe = requests.get(
        f"{environment.host}{API}/auth/me",
        cookies=_pool[0],
        headers={"X-Forwarded-For": _next_ip()},
        timeout=30,
    )
    if probe.status_code == 401:
        raise RuntimeError(
            "pooled sessions are expired (401 on /auth/me). Access tokens last "
            "15 min — re-run with SEED=1 (the default) to seed fresh sessions."
        )
    probe.raise_for_status()
    _account_cycle = itertools.cycle(_pool)


@events.test_start.add_listener
def _on_test_start(environment, **_kwargs) -> None:
    """Load the pool and, if REQUEST_TARGET is set, stop at the target.

    NB: in distributed mode (``--processes``) this fires on the master only;
    worker processes load the pool lazily in ``ApiUser.on_start``.
    """
    _load_pool(environment)
    if REQUEST_TARGET > 0 and hasattr(environment.runner, "stats"):
        import gevent

        def _watch() -> None:
            while True:
                gevent.sleep(5)
                total = environment.runner.stats.total.num_requests
                if total >= REQUEST_TARGET:
                    print(
                        f"REQUEST_TARGET reached: {total} >= {REQUEST_TARGET} "
                        "— stopping."
                    )
                    environment.runner.quit()
                    return

        gevent.spawn(_watch)


class ApiUser(HttpUser):
    """Common wiring: pooled session, CSRF header, AI guard."""

    abstract = True

    def on_start(self) -> None:
        if _account_cycle is None:  # worker process under --processes
            _load_pool(self.environment)
        assert _account_cycle is not None, "account pool was not built"
        self._cookies = next(_account_cycle)
        self.client.cookies.update(self._cookies)

    def _headers(self) -> dict[str, str]:
        headers = {
            # Unsafe methods need the double-submit CSRF header mirrored from
            # the cookie, exactly like the real frontend does.
            "X-CSRF-Token": self._cookies.get("csrf_token", "")
        }
        if UNIQUE_IPS:
            headers["X-Forwarded-For"] = _next_ip()
        return headers

    def api(self, method: str, path: str, *, name: str, **kwargs):
        """Issue a request, refusing outright to touch a token-spending path.

        Exception: POST /plans is allowed when the stack is provably pointed at
        the mock LLM (MOCK_LLM set by the operator AND MOCK_VERIFIED set by the
        canary in run.sh) — that is the whole point of the E2E mode.
        """
        if _is_ai_path(method, path):
            mock_ok = (
                MOCK_LLM
                and MOCK_VERIFIED
                and method.upper() == "POST"
                and path == f"{API}/plans"
            )
            if not mock_ok:
                raise RuntimeError(
                    f"BLOCKED: {method} {path} calls an LLM and would cost money. "
                    "The load test is AI-free by design — see perf/README.md."
                )
        return self.client.request(
            method, path, headers=self._headers(), name=name, **kwargs
        )


class BrowsingUser(ApiUser):
    """A teacher browsing subjects/plans (read-heavy, some writes)."""

    weight = 10
    wait_time = between(THINK_MIN, THINK_MAX)

    @task(6)
    def list_subjects(self) -> None:
        self.api("GET", f"{API}/subjects", name="GET /subjects")

    @task(4)
    def list_plans(self) -> None:
        self.api("GET", f"{API}/plans", name="GET /plans")

    @task(3)
    def me(self) -> None:
        self.api("GET", f"{API}/auth/me", name="GET /auth/me")

    @task(2)
    def ai_health(self) -> None:
        # Provider status = DB row + circuit-breaker state. No LLM call.
        self.api("GET", f"{API}/ai/health", name="GET /ai/health")

    @task(2)
    def liveness(self) -> None:
        self.api("GET", "/health", name="GET /health")

    @task(1)
    def create_subject(self) -> None:
        self.api(
            "POST",
            f"{API}/subjects",
            name="POST /subjects",
            json={"name": f"S-{uuid.uuid4().hex[:6]}"},
        )


class PlannerUser(ApiUser):
    """The full generation pipeline: POST /plans → planner (mock LLM) →
    Celery fan-out → poll GET /generations/{id}.

    Off by default (PLAN_WEIGHT=0); only runs against a canary-verified mock —
    ``ApiUser.api`` raises otherwise. Each iteration creates one plan (1 sync
    mock call) and queues 4 item-generation Celery tasks (4 async mock calls),
    then polls the run twice — so one iteration ≈ 3 HTTP requests + 4 tasks.
    """

    weight = PLAN_WEIGHT
    wait_time = between(2.0, 4.0)

    def on_start(self) -> None:
        super().on_start()
        resp = self.api("GET", f"{API}/subjects?limit=1", name="GET /subjects")
        items = resp.json() if resp.status_code == 200 else []
        self._subject_id = items[0]["uuid"] if items else None

    @task
    def create_plan_and_poll(self) -> None:
        if self._subject_id is None:
            return
        resp = self.api(
            "POST",
            f"{API}/plans",
            name="POST /plans (mock LLM)",
            json={
                "subject_id": self._subject_id,
                "starts_at": "2026-03-01",
                "ends_at": "2026-03-29",
                "class_duration": 50,
                "class_per_week": 2,
                "input": "Plan an introductory four-week unit for this subject.",
            },
        )
        if resp.status_code != 201:
            return
        generation = (resp.json() or {}).get("generation")
        if not generation:
            raise RuntimeError("plan created but no generation was kicked off")
        gen_id = generation["uuid"]
        # Poll like the frontend does; items complete asynchronously on the
        # worker, so this samples the queue latency rather than waiting it out.
        for _ in range(2):
            time.sleep(1.0)
            self.api(
                "GET",
                f"{API}/generations/{gen_id}",
                name="GET /generations/{id}",
            )


class AuthUser(ApiUser):
    """Deliberate argon2 pressure. Off by default (AUTH_WEIGHT=0)."""

    weight = AUTH_WEIGHT
    wait_time = between(1.0, 2.0)

    @task
    def register(self) -> None:
        email = f"churn-{uuid.uuid4().hex[:12]}@load.example.com"
        self.api(
            "POST",
            f"{API}/auth/register",
            name="POST /auth/register",
            json={"name": "Churn", "email": email, "password": "Senha@123"},
        )


# --------------------------------------------------------------------------
# Capacity discovery — ramp until an SLO breaks, then report the ceiling
# --------------------------------------------------------------------------
_samples: list[dict[str, float]] = []
_breach: dict[str, float] | None = None


def _probe(environment) -> tuple[float, float, float]:
    """One instantaneous reading of locust's ~10s sliding window."""
    total = environment.stats.total
    rps = total.current_rps or 0.0
    fails = total.current_fail_per_sec or 0.0
    p95 = float(total.get_current_response_time_percentile(0.95) or 0.0)
    return rps, p95, (fails / rps * 100.0) if rps else 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _summarise(
    users: int, probes: list[tuple[float, float, float]]
) -> dict[str, float]:
    """Median of several readings taken across the step's steady-state tail.

    A single reading is too noisy to rank steps by: one 10s window that happens
    to catch a GC pause or host CPU contention can make a step look slower than
    the busier step after it. The median over the tail is stable enough that the
    throughput curve is monotonic.
    """
    return {
        "users": users,
        "rps": _median([p[0] for p in probes]),
        "p95": _median([p[1] for p in probes]),
        "fail_pct": _median([p[2] for p in probes]),
    }


if SHAPE == "step":

    class StepLoadShape(LoadTestShape):
        """+STEP_USERS every STEP_TIME seconds until an SLO breaks."""

        def __init__(self) -> None:
            super().__init__()
            self._probes: list[tuple[float, float, float]] = []
            self._done: set[int] = set()
            self._warned = False

        def tick(self):
            global _breach
            run_time = self.get_run_time()
            if run_time < WARMUP_SECONDS:
                if not self._warned:
                    self._warned = True
                    print(f"  warming up for {WARMUP_SECONDS}s (not measured) ...")
                return (STEP_START, STEP_SPAWN)

            run_time -= WARMUP_SECONDS
            step = int(run_time // STEP_TIME)
            users = STEP_START + step * STEP_USERS
            if users > STEP_MAX:
                return None

            elapsed_in_step = run_time - step * STEP_TIME
            # Ignore the ramp; probe once per tick across the steady-state tail.
            if elapsed_in_step >= SETTLE_SECONDS:
                self._probes.append(_probe(self.runner.environment))

            if elapsed_in_step >= STEP_TIME - 1 and step not in self._done:
                self._done.add(step)
                sample = _summarise(users, self._probes)
                self._probes = []
                _samples.append(sample)
                ok = sample["p95"] <= SLO_P95_MS and sample["fail_pct"] <= SLO_FAIL_PCT
                print(
                    f"  step {users:>4} users | {sample['rps']:>7.1f} rps | "
                    f"p95 {sample['p95']:>7.0f}ms | fail {sample['fail_pct']:>5.2f}% | "
                    f"{'OK' if ok else 'SLO BREACH'}"
                )
                if not ok:
                    _breach = sample
                    return None  # ceiling found — stop rather than burn time

            return (users, STEP_SPAWN)


@events.test_stop.add_listener
def _report(environment, **_kwargs) -> None:
    if SHAPE != "step" or not _samples:
        return
    print("\n" + "=" * 68)
    print(
        "CAPACITY REPORT — AI-free paths, SLO: "
        f"p95 <= {SLO_P95_MS:.0f}ms and failures <= {SLO_FAIL_PCT}%"
    )
    print("=" * 68)
    print(f"{'users':>6} {'rps':>9} {'p95 (ms)':>10} {'fail %':>8}  verdict")
    passing = []
    for s in _samples:
        ok = s["p95"] <= SLO_P95_MS and s["fail_pct"] <= SLO_FAIL_PCT
        if ok:
            passing.append(s)
        print(
            f"{s['users']:>6.0f} {s['rps']:>9.1f} {s['p95']:>10.0f} "
            f"{s['fail_pct']:>8.2f}  {'OK' if ok else 'BREACH'}"
        )
    print("-" * 68)
    if passing:
        best = passing[-1]
        print(
            f"Sustained: {best['users']:.0f} concurrent users "
            f"at {best['rps']:.0f} rps (p95 {best['p95']:.0f}ms, "
            f"{best['fail_pct']:.2f}% failures)."
        )
    else:
        print("No step met the SLO — lower STEP_START or relax SLO_P95_MS.")
    if _breach:
        print(
            f"Degraded at: {_breach['users']:.0f} users "
            f"(p95 {_breach['p95']:.0f}ms, {_breach['fail_pct']:.2f}% failures)."
        )
    else:
        print(
            f"No breach up to STEP_MAX={STEP_MAX} — the ceiling is higher; "
            "raise STEP_MAX to find it."
        )
    print("=" * 68)
    sys.stdout.flush()
