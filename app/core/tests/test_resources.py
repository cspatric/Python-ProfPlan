"""The CPU grant is read from the cgroup, so sizing follows the container."""

from pathlib import Path

import pytest

from app.core import resources


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_a_cgroup_v2_quota_is_read_as_a_fraction_of_a_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # "50000 100000" is docker's `cpus: "0.5"`.
    monkeypatch.setattr(
        resources, "_CGROUP_V2_MAX", _write(tmp_path / "cpu.max", "50000 100000\n")
    )
    assert resources.available_cpus() == pytest.approx(0.5)


def test_an_unlimited_cgroup_v2_falls_back_to_the_host_core_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        resources, "_CGROUP_V2_MAX", _write(tmp_path / "cpu.max", "max 100000\n")
    )
    monkeypatch.setattr(resources, "_CGROUP_V1_QUOTA", tmp_path / "absent")
    monkeypatch.setattr(resources.os, "cpu_count", lambda: 8)
    assert resources.available_cpus() == 8.0


def test_cgroup_v1_is_read_when_v2_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(resources, "_CGROUP_V2_MAX", tmp_path / "absent")
    monkeypatch.setattr(
        resources,
        "_CGROUP_V1_QUOTA",
        _write(tmp_path / "cfs_quota_us", "200000\n"),
    )
    monkeypatch.setattr(
        resources,
        "_CGROUP_V1_PERIOD",
        _write(tmp_path / "cfs_period_us", "100000\n"),
    )
    assert resources.available_cpus() == pytest.approx(2.0)


def test_a_v1_quota_of_minus_one_means_unlimited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(resources, "_CGROUP_V2_MAX", tmp_path / "absent")
    monkeypatch.setattr(
        resources, "_CGROUP_V1_QUOTA", _write(tmp_path / "quota", "-1\n")
    )
    monkeypatch.setattr(
        resources, "_CGROUP_V1_PERIOD", _write(tmp_path / "period", "100000\n")
    )
    monkeypatch.setattr(resources.os, "cpu_count", lambda: 4)
    assert resources.available_cpus() == 4.0


def test_garbage_in_the_cgroup_file_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        resources, "_CGROUP_V2_MAX", _write(tmp_path / "cpu.max", "not a quota\n")
    )
    monkeypatch.setattr(resources, "_CGROUP_V1_QUOTA", tmp_path / "absent")
    monkeypatch.setattr(resources.os, "cpu_count", lambda: 2)
    assert resources.available_cpus() == 2.0


def test_a_fractional_grant_still_allows_one_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A container on half a core must still be able to log somebody in."""
    monkeypatch.setattr(resources, "available_cpus", lambda: 0.25)
    assert resources.cpu_bound_concurrency(minimum=1, per_cpu=1) == 1


def test_concurrency_scales_with_the_grant_and_respects_the_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resources, "available_cpus", lambda: 4.0)
    assert resources.cpu_bound_concurrency(per_cpu=2) == 8
    monkeypatch.setattr(resources, "available_cpus", lambda: 1.0)
    assert resources.cpu_bound_concurrency(minimum=6, per_cpu=2) == 6
