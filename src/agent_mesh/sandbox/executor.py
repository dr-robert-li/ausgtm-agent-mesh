"""Hardened prompt-to-code executor (Docker cgroup isolation).

Runs a snippet of generated Python inside a short-lived, hardened Docker
container: cgroup memory cap (equal ``--memory``/``--memory-swap``), no network,
read-only rootfs, non-root user, all capabilities dropped. The snippet is mounted
read-only and the only writable surface is an ephemeral ``/work`` tmpfs.

D-03 (refuse-to-run-unbounded): the executor NEVER runs unbounded. When Docker is
absent it raises :class:`SandboxUnavailable` rather than falling back to an uncapped
native subprocess — closing the previous fail-open ``RLIMIT_AS`` bug. Docker Desktop
on macOS runs a Linux VM, so ``--memory`` cgroup enforcement works on macOS too when
Docker is running; the refuse path is only for when Docker is truly absent.

This is the POC executor — see the package docstring and production caveats §1.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from agent_mesh.contracts.models import ProposedPatch


class SandboxUnavailable(RuntimeError):
    """Raised when no hardened isolation boundary is available.

    The executor refuses to run unbounded (D-03): when Docker is absent it raises
    this rather than falling back to an uncapped native subprocess.
    """


@dataclass
class SandboxLimits:
    timeout_s: int = 30
    max_cpu_seconds: int = 20
    max_memory_mb: int = 512
    max_output_bytes: int = 1_000_000


@dataclass
class CodeExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    artifact_paths: list[str] = field(default_factory=list)
    timed_out: bool = False


_SANDBOX_IMAGE = "python:3.11-slim"


def _docker_run_argv(snippet_dir: str, limits: SandboxLimits, container_name: str) -> list[str]:
    """Build the hardened ``docker run`` argv for ``snippet_dir/snippet.py``.

    ``--memory`` and ``--memory-swap`` are set equal (Pitfall 2: an unequal/unset
    swap limit defeats the memory cap). The snippet is bind-mounted read-only at
    ``/snippet`` (a path distinct from the writable ``/work`` tmpfs — mounting both
    a tmpfs and a bind at the same path is rejected by Docker).

    ``--name`` makes the daemon-owned container addressable so a wall-clock timeout
    can ``docker kill`` it (CR-01: a SIGKILL to the foreground ``docker run`` client
    does NOT stop the container, and ``--rm`` only reaps it on exit). ``--ulimit cpu``
    enforces ``max_cpu_seconds`` as a hard RLIMIT_CPU inside the container so a
    busy-loop is contained on CPU time independently of the wall clock (WR-01).
    """
    mem = f"{limits.max_memory_mb}m"
    return [
        "docker",
        "run",
        "--rm",
        f"--name={container_name}",  # addressable for docker kill on timeout (CR-01)
        f"--memory={mem}",
        f"--memory-swap={mem}",  # MUST equal --memory or the cap is a no-op (Pitfall 2)
        f"--ulimit=cpu={limits.max_cpu_seconds}",  # hard CPU-seconds cap (WR-01)
        "--network=none",
        "--read-only",
        "--tmpfs",
        "/work:rw,size=64m",
        "--user",
        "65534:65534",
        "--cap-drop=ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit=128",
        "--workdir",
        "/work",
        "-v",
        f"{snippet_dir}:/snippet:ro",
        _SANDBOX_IMAGE,
        "python",
        "-I",
        "/snippet/snippet.py",
    ]


def _force_remove_container(container_name: str) -> None:
    """Best-effort ``docker rm -f`` to stop+reap a container the timeout abandoned.

    A ``subprocess`` timeout SIGKILLs only the ``docker run`` client; the
    daemon-owned container keeps running (CR-01). ``docker rm -f`` both kills and
    removes it in one call. Bounded and swallow-all: cleanup must never mask the
    original timeout outcome.
    """
    try:
        subprocess.run(  # noqa: S603,S607 - fixed argv, container_name is a uuid hex
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def execute_code(code: str, limits: SandboxLimits | None = None) -> CodeExecutionResult:
    """Execute ``code`` inside a hardened Docker container.

    No writes are applied to the repo or any external system; the only writable
    surface inside the container is the ephemeral ``/work`` tmpfs.

    Raises :class:`SandboxUnavailable` when Docker is absent — the executor NEVER
    falls back to an uncapped native subprocess (D-03).
    """
    limits = limits or SandboxLimits()

    if shutil.which("docker") is None:
        raise SandboxUnavailable(
            "Docker required for sandbox execution; refusing to run unbounded"
        )

    container_name = f"agent-mesh-sbx-{uuid.uuid4().hex}"
    with tempfile.TemporaryDirectory(prefix="agent-mesh-sbx-") as workdir:
        script = Path(workdir) / "snippet.py"
        script.write_text(code)
        try:
            proc = subprocess.run(
                _docker_run_argv(workdir, limits, container_name),
                capture_output=True,
                text=True,
                timeout=limits.timeout_s,
                check=False,  # noqa: S603 - controlled argv; snippet mounted read-only
            )
        except subprocess.TimeoutExpired as exc:
            # The subprocess timeout killed only the `docker run` client; the
            # daemon-owned container is still running. Force-stop+reap it (CR-01).
            _force_remove_container(container_name)
            raw = exc.stdout or ""
            stdout = raw.decode() if isinstance(raw, bytes) else raw
            return CodeExecutionResult(
                exit_code=124,
                stdout=stdout,
                stderr="timed out",
                timed_out=True,
            )

        # Artifacts written inside the container land on the ephemeral /work tmpfs
        # and do NOT survive --rm back to the host; artifact_paths is empty on the
        # Docker path (known limitation — see SUMMARY).
        return CodeExecutionResult(
            exit_code=proc.returncode,
            stdout=proc.stdout[: limits.max_output_bytes],
            stderr=proc.stderr[: limits.max_output_bytes],
            artifact_paths=[],
        )


def propose_patch(
    *, task_id: str, tenant_id: str, description: str, diff: str, artifacts: list[str] | None = None
) -> ProposedPatch:
    """Wrap a generated diff/artifact as a ProposedPatch. ``approval_required`` is
    always true: the patch is NOT applied until approved."""
    return ProposedPatch(
        task_id=task_id,
        tenant_id=tenant_id,
        description=description,
        diff=diff,
        artifact_paths=artifacts or [],
        approval_required=True,
    )
