"""How much CPU this process actually has.

Every sizing decision that used to be a hand-maintained number wants the same
input: how many cores the *container* was granted, not how many the host owns.
``os.cpu_count()`` answers the second question, which is why a container limited
to ``cpus: "1.0"`` on an 8-core host still forks eight Celery children and still
lets eight Argon2 hashes fight over one core's worth of quota.

The grant is readable from the cgroup, so nothing here needs configuring: the
number re-derives itself when the limit changes. Both cgroup versions are
handled because Docker Desktop and older kernels still ship v1, and the answer
falls back to the host core count when neither file is present (bare metal, a
Mac, a CI runner).
"""

import os
from pathlib import Path

_CGROUP_V2_MAX = Path("/sys/fs/cgroup/cpu.max")
_CGROUP_V1_QUOTA = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
_CGROUP_V1_PERIOD = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _cgroup_v2_cpus() -> float | None:
    """Parse ``cpu.max``: "<quota> <period>", or "max <period>" when unlimited."""
    try:
        quota_raw, period_raw = _CGROUP_V2_MAX.read_text().split()
    except (OSError, ValueError):
        return None
    if quota_raw == "max":
        return None
    try:
        quota, period = int(quota_raw), int(period_raw)
    except ValueError:
        return None
    return quota / period if period > 0 else None


def _cgroup_v1_cpus() -> float | None:
    """Parse the v1 pair; a quota of -1 means unlimited."""
    quota = _read_int(_CGROUP_V1_QUOTA)
    period = _read_int(_CGROUP_V1_PERIOD)
    if quota is None or period is None or quota <= 0 or period <= 0:
        return None
    return quota / period


def available_cpus() -> float:
    """The CPU grant of this container, or the host core count when unlimited.

    Fractional by design: a container limited to ``cpus: "0.5"`` gets 0.5, and
    callers decide how to round for their own purpose.
    """
    for source in (_cgroup_v2_cpus, _cgroup_v1_cpus):
        cpus = source()
        if cpus is not None and cpus > 0:
            return cpus
    return float(os.cpu_count() or 1)


def cpu_bound_concurrency(*, minimum: int = 1, per_cpu: int = 1) -> int:
    """How many CPU-bound operations may run at once in this process.

    Rounds the grant UP so a fractional limit still allows one operation — a
    container with ``cpus: "0.5"`` must still be able to log somebody in — and
    never returns less than ``minimum``.
    """
    return max(minimum, int(-(-available_cpus() * per_cpu // 1)))
