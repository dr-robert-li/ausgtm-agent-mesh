"""SBX-01 coverage for the hardened sandbox executor.

Two tests (D-03a):
- ``test_refuses_unbounded`` (always-on): with Docker forced-absent, ``execute_code``
  raises ``SandboxUnavailable`` — it NEVER runs an uncapped native subprocess. Runs
  everywhere, including macOS ``make test`` with no Docker.
- ``test_oom_enforced`` (Docker-gated): an over-allocation snippet is OOM-killed by the
  cgroup memory cap and surfaces as exit code 137. Skips cleanly when Docker is absent.

The Docker skip is INLINE here (no conftest fixture) to keep this file self-contained
and avoid any overlap with other plans in the wave.

- ``test_timeout_kills_container`` (Docker-gated, CR-01): a snippet that outlives the
  wall-clock timeout is force-stopped — the daemon-owned container does NOT survive the
  ``docker run`` client's SIGKILL. Closes the containment hole the OOM-only test missed.
"""

from __future__ import annotations

import shutil
import subprocess
import types

import pytest

from agent_mesh.sandbox import executor
from agent_mesh.sandbox.executor import (
    SandboxLimits,
    SandboxUnavailable,
    execute_code,
)


def _container_exists(name: str) -> bool:
    """True if a container named ``name`` exists (any state) on the daemon."""
    out = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return name in out.stdout.split()


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


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker not available"
)
def test_timeout_kills_container(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wall-clock timeout force-stops the daemon-owned container (CR-01).

    A ``subprocess`` timeout SIGKILLs only the ``docker run`` client; the container
    keeps running unless the executor explicitly kills it. We pin the container name
    so we can assert it is gone after the timed-out call returns.
    """
    name = "agent-mesh-sbx-pytestcontainment"
    # Pin the uuid so the executor's container name is predictable.
    monkeypatch.setattr(
        executor.uuid, "uuid4", lambda: types.SimpleNamespace(hex="pytestcontainment")
    )
    # Defensive cleanup: never leak a container even if the assertion fails.
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)

    try:
        # Snippet sleeps far longer than the timeout; container must be up, then killed.
        limits = SandboxLimits(timeout_s=5)
        result = execute_code("import time\ntime.sleep(120)\n", limits=limits)

        assert result.timed_out is True
        assert result.exit_code == 124
        assert not _container_exists(name), (
            "container survived the timeout — CR-01 containment hole is open: "
            "the docker-run client was killed but the daemon-owned container kept running"
        )
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
