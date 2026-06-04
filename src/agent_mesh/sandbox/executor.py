"""Subprocess code executor with conservative limits.

Runs a snippet of generated Python in an isolated, ephemeral working directory
with CPU/memory/time caps applied via ``resource`` limits in a preexec hook
(POSIX). Captures stdout/stderr/exit code and any files written to the work dir
as artifacts.

This is the POC executor. It is deliberately simple and is NOT a production
isolation boundary — see the package docstring and production caveats §1.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from agent_mesh.contracts.models import ProposedPatch


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


def _preexec(limits: SandboxLimits):  # pragma: no cover - POSIX-only, exercised at runtime
    def _apply() -> None:
        import resource

        cpu = limits.max_cpu_seconds
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        mem = limits.max_memory_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        except (ValueError, OSError):
            # Some platforms reject RLIMIT_AS; fail open on the memory cap only.
            pass

    return _apply


def execute_code(code: str, limits: SandboxLimits | None = None) -> CodeExecutionResult:
    """Execute ``code`` in an isolated temp dir. No writes are applied to the
    repo or any external system; only the ephemeral work dir is touched."""
    limits = limits or SandboxLimits()
    with tempfile.TemporaryDirectory(prefix="agent-mesh-sbx-") as workdir:
        script = Path(workdir) / "snippet.py"
        script.write_text(code)
        preexec = _preexec(limits) if sys.platform != "win32" else None
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(script)],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=limits.timeout_s,
                preexec_fn=preexec,  # noqa: S603 - controlled args, isolated workdir
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raw = exc.stdout or ""
            stdout = raw.decode() if isinstance(raw, bytes) else raw
            return CodeExecutionResult(
                exit_code=124,
                stdout=stdout,
                stderr="timed out",
                timed_out=True,
            )

        artifacts = [
            str(p.name) for p in Path(workdir).iterdir() if p.name != "snippet.py"
        ]
        return CodeExecutionResult(
            exit_code=proc.returncode,
            stdout=proc.stdout[: limits.max_output_bytes],
            stderr=proc.stderr[: limits.max_output_bytes],
            artifact_paths=artifacts,
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
