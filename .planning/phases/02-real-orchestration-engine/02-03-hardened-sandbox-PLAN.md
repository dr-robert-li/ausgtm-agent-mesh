---
phase: 02-real-orchestration-engine
plan: 03
type: execute
wave: 1
depends_on: []
files_modified:
  - src/agent_mesh/sandbox/executor.py
  - tests/test_sandbox.py
autonomous: true
requirements: [SBX-01]
must_haves:
  truths:
    - "The executor NEVER runs unbounded: when Docker is absent (or rlimit is rejected) it refuses/raises rather than falling back to an uncapped native subprocess"
    - "When Docker is present, code executes via the hardened cgroup container path; an over-allocation snippet is OOM-killed (exit 137)"
    - "make test / make smoke stay green on macOS with no Docker — the Docker-enforcement test skips cleanly; the refuse-to-run-unbounded invariant is tested everywhere"
  artifacts:
    - path: "src/agent_mesh/sandbox/executor.py"
      provides: "Hardened Docker cgroup execution path + refuse-to-run-unbounded (replaces the fail-open RLIMIT_AS block)"
      contains: "--memory-swap"
    - path: "tests/test_sandbox.py"
      provides: "SBX-01 coverage: always-on refuse-unbounded + Docker-gated OOM-137"
      contains: "exit"
  key_links:
    - from: "src/agent_mesh/sandbox/executor.py"
      to: "docker"
      via: "shutil.which('docker') gate -> cgroup run or refuse"
      pattern: "shutil.which"
    - from: "tests/test_sandbox.py"
      to: "src/agent_mesh/sandbox/executor.py"
      via: "execute_code refuses when docker absent"
      pattern: "execute_code"
---

<objective>
Close the fail-open memory-cap bug in the sandbox executor and make the hardened Docker
cgroup container path the only real execution path (D-03). The executor MUST NEVER run
unbounded: replace the silent `except (ValueError, OSError): pass` fail-open on `RLIMIT_AS`
(executor.py:49-51) with a refuse-to-run behaviour — when Docker is absent (or rlimit is
rejected) it raises a clear `SandboxUnavailable`, NEVER an uncapped native subprocess.

macOS framing trap (RF-4): Docker Desktop on macOS runs a Linux VM, so `--memory` cgroup
enforcement DOES work on macOS when Docker is running. The refuse path is for when Docker is
truly absent — it is the non-negotiable invariant tested everywhere.

This plan is independent of 02-01/02-02 (no shared files); it runs in Wave 1. The Docker skip
is INLINE in test_sandbox.py (no conftest edit), so there is zero file overlap with 02-01.

Purpose: SBX-01 — enforce the memory limit without failing open, via the hardened container path.
Output: hardened executor.py (Docker cgroup path + refuse-unbounded) and tests/test_sandbox.py.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/02-real-orchestration-engine/02-RESEARCH.md
@.planning/phases/02-real-orchestration-engine/02-PATTERNS.md
@src/agent_mesh/sandbox/executor.py

<interfaces>
<!-- Contracts to preserve in executor.py -->

SandboxLimits (executor.py:23-28) — preserve: timeout_s=30, max_cpu_seconds=20, max_memory_mb=512, max_output_bytes=1_000_000.
CodeExecutionResult (executor.py:31-37) — preserve: exit_code, stdout, stderr, artifact_paths, timed_out.
execute_code(code, limits=None) -> CodeExecutionResult (executor.py:56) — same signature; behaviour hardened.
propose_patch(...) -> ProposedPatch with approval_required=True (executor.py:95-107) — UNCHANGED (no auto-apply).

The fail-open block to DELETE (executor.py:47-51):
    try: resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    except (ValueError, OSError): pass   # <- D-03 forbids this silent fail-open

Hardened Docker invocation (RF-4) — flags that MUST appear:
  --memory=Nm --memory-swap=Nm   (equal — unequal/unset swap defeats the cap: the trap)
  --network=none  --read-only  --tmpfs /work:rw,size=64m
  --user 65534:65534  --cap-drop=ALL  --security-opt no-new-privileges  --pids-limit=128
  --workdir /work  python:3.11-slim   python -I /work/snippet.py
  wall-clock timeout via subprocess timeout=limits.timeout_s (existing)
  OOM over-allocation -> container exit code 137
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Replace fail-open RLIMIT_AS with the hardened Docker cgroup path + refuse-to-run-unbounded</name>
  <files>src/agent_mesh/sandbox/executor.py</files>
  <read_first>
    - src/agent_mesh/sandbox/executor.py (whole file — _preexec 40-53 with the fail-open block 47-51; execute_code 56-92; SandboxLimits 23-28; propose_patch 95-107 stays unchanged)
    - .planning/phases/02-real-orchestration-engine/02-RESEARCH.md (RF-4 exact Docker invocation + the macOS-via-Docker enforcement note + refuse-to-run-unbounded behaviour + Pitfall 2 --memory-swap)
    - .planning/phases/02-real-orchestration-engine/02-PATTERNS.md (executor.py MODIFY section — the fail-open block to delete + the replacement flags)
  </read_first>
  <behavior>
    - Docker present (shutil.which("docker") is not None): execute_code runs the snippet in a hardened container with the cgroup memory cap; returns CodeExecutionResult with the container exit code; an over-allocation snippet yields exit_code 137
    - Docker absent: execute_code raises SandboxUnavailable (a new exception) — it NEVER runs the uncapped native subprocess
    - timeout still honoured via subprocess timeout=limits.timeout_s (returns the existing timed_out result on TimeoutExpired)
    - propose_patch unchanged (approval_required=True)
  </behavior>
  <action>
    Add a SandboxUnavailable exception class. Replace the _preexec fail-open block and the native-subprocess
    execution in execute_code with the hardened Docker cgroup path: detect Docker via shutil.which("docker");
    if absent, raise SandboxUnavailable("Docker required for sandbox execution; refusing to run unbounded")
    — do NOT fall back to an uncapped native subprocess (D-03 closes the fail-open). When Docker is present,
    write the snippet to a temp dir and run `docker run --rm --memory={N}m --memory-swap={N}m --network=none
    --read-only --tmpfs /work:rw,size=64m --user 65534:65534 --cap-drop=ALL --security-opt no-new-privileges
    --pids-limit=128 --workdir /work -v <snippetdir>:/work:ro python:3.11-slim python -I /work/snippet.py`
    where N = limits.max_memory_mb; --memory-swap MUST equal --memory (Pitfall 2 — unequal/unset swap defeats
    the cap). Keep the subprocess timeout=limits.timeout_s wall-clock and the existing TimeoutExpired ->
    timed_out result. Return CodeExecutionResult with the container's exit_code (an OOM kill surfaces as 137),
    stdout/stderr truncated to max_output_bytes, and artifact discovery from the work dir. Leave propose_patch
    and SandboxLimits/CodeExecutionResult shapes unchanged. The rlimit native path is removed entirely — it is
    no longer a fallback (macOS rejects RLIMIT_AS and Docker is the only real enforcement boundary).
  </action>
  <verify>
    <automated>grep -c "SandboxUnavailable" src/agent_mesh/sandbox/executor.py</automated>
    <automated>grep -c "shutil.which" src/agent_mesh/sandbox/executor.py</automated>
    <automated>grep -c -- "--memory-swap" src/agent_mesh/sandbox/executor.py</automated>
    <automated>test $(grep -c "except (ValueError, OSError):" src/agent_mesh/sandbox/executor.py) -eq 0</automated>
    <automated>python -c "import ast; ast.parse(open('src/agent_mesh/sandbox/executor.py').read())"</automated>
  </verify>
  <acceptance_criteria>
    - executor.py defines a SandboxUnavailable exception and execute_code raises it when shutil.which("docker") is None (no native-subprocess fallback)
    - executor.py contains the equal `--memory` and `--memory-swap` flags plus --network=none, --read-only, --user 65534:65534, --cap-drop=ALL
    - the fail-open `except (ValueError, OSError): pass` block is gone (grep returns 0)
    - propose_patch still returns approval_required=True; SandboxLimits / CodeExecutionResult shapes unchanged
  </acceptance_criteria>
  <done>The sandbox enforces its memory limit via the hardened Docker cgroup path and refuses to run unbounded when Docker is absent — the fail-open bug is closed.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: SBX-01 tests — always-on refuse-unbounded + Docker-gated OOM-137</name>
  <files>tests/test_sandbox.py</files>
  <read_first>
    - src/agent_mesh/sandbox/executor.py (the hardened execute_code + SandboxUnavailable from Task 1)
    - tests/conftest.py (the pg_dsn skip-when-unset shape — borrow the skip-cleanly pattern; do NOT add a fixture to conftest, keep the docker skip INLINE in this test file)
    - .planning/phases/02-real-orchestration-engine/02-RESEARCH.md (RF-4 "Two tests (D-03a)"; Validation Architecture SBX-01 rows; Pitfall 2 assert exit 137)
    - .planning/phases/02-real-orchestration-engine/02-PATTERNS.md (test_sandbox.py section — always-on monkeypatch refuse + Docker-gated OOM)
  </read_first>
  <behavior>
    - test_refuses_unbounded (always-on, runs on macOS make test): monkeypatch shutil.which to return None -> execute_code raises SandboxUnavailable (NEVER runs an uncapped subprocess)
    - test_oom_enforced (Docker-gated, skips when docker absent): an over-allocation snippet -> CodeExecutionResult.exit_code == 137
  </behavior>
  <action>
    Create tests/test_sandbox.py. test_refuses_unbounded: use monkeypatch.setattr on the executor module's
    shutil.which (or shutil.which) to return None, then pytest.raises(SandboxUnavailable): execute_code("print(1)").
    This is always-on and MUST pass in this env (no Docker). test_oom_enforced: decorate with
    @pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available") — keep this skip INLINE in
    the test file, do NOT add a conftest fixture; run execute_code with a snippet that allocates well beyond
    limits.max_memory_mb (e.g. a large bytearray/list) and assert the returned exit_code == 137 (OOM kill).
    Import SandboxUnavailable and execute_code from agent_mesh.sandbox.executor.
  </action>
  <verify>
    <automated>grep -c "skipif" tests/test_sandbox.py</automated>
    <automated>grep -c "SandboxUnavailable" tests/test_sandbox.py</automated>
    <automated>grep -c "137" tests/test_sandbox.py</automated>
    <automated>python -m pytest -q tests/test_sandbox.py::test_refuses_unbounded -x</automated>
    <automated>python -m pytest -q tests/ -x</automated>
  </verify>
  <acceptance_criteria>
    - tests/test_sandbox.py::test_refuses_unbounded exits 0 in THIS env (no Docker) — asserts execute_code raises SandboxUnavailable when shutil.which returns None
    - test_oom_enforced is decorated with @pytest.mark.skipif(shutil.which("docker") is None, ...) (inline, not via conftest) and asserts exit_code == 137
    - the Docker-gated test SKIPS cleanly (not fails) when Docker is absent
    - `python -m pytest -q tests/` exits 0 in this env
  </acceptance_criteria>
  <done>SBX-01 is proven: the always-on test guarantees the executor refuses to run unbounded with no Docker, and the Docker-gated test asserts real cgroup OOM enforcement (exit 137) where Docker exists.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| generated code → host | untrusted prompt-to-code crosses into execution; the container is the only isolation boundary |
| executor → Docker daemon | execute_code invokes `docker run` with hardened flags |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-03-01 | DoS | sandboxed code exhausts host memory | mitigate | cgroup `--memory=Nm --memory-swap=Nm` (equal — Pitfall 2); OOM → exit 137. Refuse-to-run-unbounded when Docker absent (no uncapped fallback). |
| T-02-03-02 | Info disclosure / Exfiltration | sandboxed code reaches the network | mitigate | `--network=none` — no egress from the container. |
| T-02-03-03 | Tampering | sandboxed code writes the host/rootfs | mitigate | `--read-only` rootfs + `--tmpfs /work:rw,size=64m` (only writable surface is the ephemeral workdir); snippet mounted read-only. |
| T-02-03-04 | Elevation | privilege escalation inside the container | mitigate | `--user 65534:65534` (non-root), `--cap-drop=ALL`, `--security-opt no-new-privileges`, `--pids-limit=128`. |
| T-02-03-05 | DoS / Elevation | fail-open when isolation unavailable | mitigate | execute_code raises SandboxUnavailable when Docker absent — NEVER an uncapped native subprocess (D-03; closes the executor.py:49-51 fail-open). Tested always-on. |
</threat_model>

<verification>
- `python -m pytest -q tests/test_sandbox.py::test_refuses_unbounded` exits 0 in this env (no Docker) — refuse-unbounded invariant holds.
- `python -m pytest -q tests/` exits 0; the Docker-gated OOM test skips cleanly when Docker is absent.
- `make smoke` stays green (it does not touch the sandbox path).
- executor.py contains the equal `--memory`/`--memory-swap` flags and no fail-open `except ... pass` on the memory cap.
</verification>

<success_criteria>
SBX-01 satisfied: the sandbox enforces its memory limit without failing open (refuses to run unbounded when Docker is absent) and executes via the hardened Docker cgroup container path (equal --memory/--memory-swap, network-off, read-only, non-root, cap-drop), with OOM surfacing as exit 137 on the Docker-present path.
</success_criteria>

<output>
Create `.planning/phases/02-real-orchestration-engine/02-03-SUMMARY.md` when done.
</output>
