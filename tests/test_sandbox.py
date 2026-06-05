"""SBX-01 coverage for the hardened sandbox executor.

Two tests (D-03a):
- ``test_refuses_unbounded`` (always-on): with Docker forced-absent, ``execute_code``
  raises ``SandboxUnavailable`` — it NEVER runs an uncapped native subprocess. Runs
  everywhere, including macOS ``make test`` with no Docker.
- ``test_oom_enforced`` (Docker-gated): an over-allocation snippet is OOM-killed by the
  cgroup memory cap and surfaces as exit code 137. Skips cleanly when Docker is absent.

The Docker skip is INLINE here (no conftest fixture) to keep this file self-contained
and avoid any overlap with other plans in the wave.
"""

from __future__ import annotations

import shutil

import pytest

from agent_mesh.sandbox import executor
from agent_mesh.sandbox.executor import (
    SandboxLimits,
    SandboxUnavailable,
    execute_code,
)


def test_refuses_unbounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Docker absent → refuse to run, NEVER an uncapped native subprocess (D-03).

    This is the always-on invariant: it must pass in every environment, including
    macOS ``make test`` with no Docker.
    """
    # Force Docker "absent" regardless of the host so the refuse path is exercised
    # deterministically. Patch the name the executor module resolves at call time.
    monkeypatch.setattr(executor.shutil, "which", lambda _name: None)

    with pytest.raises(SandboxUnavailable):
        execute_code("print(1)")


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker not available"
)
def test_oom_enforced() -> None:
    """Docker present → cgroup memory cap OOM-kills an over-allocation snippet (exit 137)."""
    limits = SandboxLimits(max_memory_mb=128, timeout_s=60)
    # Allocate well beyond the 128MB cap so the cgroup OOM-killer fires.
    code = "x = bytearray(800 * 1024 * 1024)\nprint(len(x))\n"
    result = execute_code(code, limits=limits)

    assert result.exit_code == 137, (
        f"expected OOM exit 137, got {result.exit_code} "
        f"(stdout={result.stdout!r}, stderr={result.stderr!r})"
    )
