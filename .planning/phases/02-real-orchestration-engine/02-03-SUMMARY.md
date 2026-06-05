---
phase: 02-real-orchestration-engine
plan: 03
subsystem: infra
tags: [sandbox, docker, cgroup, security, prompt-to-code, pytest]

# Dependency graph
requires:
  - phase: 01 (scaffold)
    provides: subprocess executor.py with fail-open RLIMIT_AS memory cap (the bug closed here)
provides:
  - Hardened Docker cgroup sandbox execution path (equal --memory/--memory-swap, network-off, read-only, non-root, cap-drop)
  - SandboxUnavailable refuse-to-run-unbounded invariant (D-03 — closes the executor.py fail-open)
  - SBX-01 test coverage (always-on refuse-unbounded + Docker-gated OOM-137)
affects: [prompt-to-code, code-writer, sandbox, E2E]

# Tech tracking
tech-stack:
  added: [docker (python:3.11-slim sandbox image)]
  patterns:
    - "Refuse-to-run-unbounded: raise rather than fall back to an uncapped path when isolation is unavailable"
    - "Hardened docker run argv builder (equal memory/memory-swap; snippet bind-mounted read-only at a path distinct from the writable tmpfs)"
    - "Inline @pytest.mark.skipif(shutil.which('docker') is None) Docker-gated test (no conftest fixture)"

key-files:
  created:
    - tests/test_sandbox.py
  modified:
    - src/agent_mesh/sandbox/executor.py

key-decisions:
  - "Docker is the only real enforcement boundary; the native rlimit path is removed entirely (macOS rejects RLIMIT_AS)"
  - "Mount snippet read-only at /snippet (distinct from the writable /work tmpfs) to avoid Docker's duplicate-mount-point rejection"
  - "max_memory_mb=128 used in the OOM test for a fast, reliable kill well below host RAM"

patterns-established:
  - "Fail-closed isolation: SandboxUnavailable raised when Docker absent — no uncapped fallback ever"
  - "Equal --memory/--memory-swap is mandatory (Pitfall 2: unequal/unset swap defeats the cap)"

requirements-completed: [SBX-01]

# Metrics
duration: 12min
completed: 2026-06-05
---

# Phase 02 Plan 03: Hardened Sandbox Summary

**Closed the fail-open memory-cap bug: the prompt-to-code executor now runs only via a hardened Docker cgroup container (equal --memory/--memory-swap, network-off, read-only, non-root, cap-drop) and refuses to run unbounded (raises SandboxUnavailable) when Docker is absent.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-05T21:53Z
- **Completed:** 2026-06-05T22:05Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- Replaced the silent `except (ValueError, OSError): pass` fail-open on `RLIMIT_AS` with a refuse-to-run-unbounded behaviour (`SandboxUnavailable`) — the executor NEVER runs an uncapped native subprocess (D-03).
- Made the hardened Docker cgroup container the only real execution path: equal `--memory`/`--memory-swap`, `--network=none`, `--read-only`, `--tmpfs /work`, `--user 65534:65534`, `--cap-drop=ALL`, `--security-opt no-new-privileges`, `--pids-limit=128`, snippet mounted read-only.
- Proved real cgroup OOM enforcement live in this environment: an over-allocation snippet is OOM-killed → exit code 137.
- Added SBX-01 coverage: an always-on refuse-unbounded test (passes with no Docker) and an inline Docker-gated OOM-137 test (skips cleanly when Docker is absent).
- `propose_patch` and the `SandboxLimits`/`CodeExecutionResult` shapes are unchanged (approval gate intact, no auto-apply).

## Task Commits

Each task was committed atomically:

1. **Task 1: Harden executor — Docker cgroup path + refuse-unbounded** - `5bebfa1` (feat)
2. **Task 2: SBX-01 tests — always-on refuse + Docker-gated OOM-137** - `a499aed` (test)

_Note: this is a TDD plan; both tasks landed green (Task 1 hardened the executor and was verified by Task 2's tests, which pass in this Docker-present env)._

## Files Created/Modified
- `src/agent_mesh/sandbox/executor.py` - Hardened Docker cgroup execution path + `SandboxUnavailable`; removed the fail-open `RLIMIT_AS` block and the native-subprocess fallback. Added `_docker_run_argv` builder.
- `tests/test_sandbox.py` - `test_refuses_unbounded` (always-on) + `test_oom_enforced` (inline `@skipif` Docker-gated, asserts exit_code == 137).

## Decisions Made
- **Docker is the only real enforcement boundary.** The native `_preexec`/`RLIMIT_AS` path is removed entirely rather than kept as a fallback — macOS rejects `RLIMIT_AS`, and a fallback would reopen the fail-open bug. When Docker is absent the executor refuses (raises) instead.
- **Distinct mount paths to avoid Docker's duplicate-mount rejection** (see Deviation 1).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Snippet bind-mount moved off `/work` to `/snippet`**
- **Found during:** Task 1 (executor hardening) — caught at the shell before writing code.
- **Issue:** The plan's action text mounted BOTH the writable tmpfs and the read-only snippet bind at `/work`. Docker rejects a duplicate mount point (`/work`) with exit 125 — never reaching the cgroup path, so the OOM-137 test would error instead of pass.
- **Fix:** Bind-mount the snippet read-only at a distinct path `/snippet` (`-v <dir>:/snippet:ro`) and run `python -I /snippet/snippet.py`; keep `--tmpfs /work` as the sole writable surface. All plan greps still match (they check flags, not the mount path).
- **Files modified:** src/agent_mesh/sandbox/executor.py
- **Verification:** Proved live at the shell (`EXIT=137`) before writing the module; `tests/test_sandbox.py` passes (2 passed) with Docker present.
- **Committed in:** 5bebfa1 (Task 1 commit)

**2. [Rule 1 - Bug] `artifact_paths` returns `[]` on the Docker path (action-text "artifact discovery" structurally superseded by RF-4 hardening)**
- **Found during:** Task 1 (executor hardening).
- **Issue:** The plan `<action>` text lists "artifact discovery from the work dir" as part of `execute_code`'s return. RF-4's hardening mandates `--read-only` rootfs plus an ephemeral `--tmpfs /work`: files the snippet writes live only inside the container's tmpfs and cannot survive `--rm` back to the host. Host-side workdir discovery (as the old native-subprocess executor did) is therefore structurally impossible on the hardened path. Returning a misleading non-empty list, or scanning the now-empty host workdir, would be incorrect.
- **Fix:** Return `artifact_paths=[]` on the Docker path and document why in the executor docstring/comment. Verified no consumer depends on `CodeExecutionResult.artifact_paths` (`grep -rn "artifact_paths\|execute_code" src/ tests/` — only the unrelated `ProposedPatch.artifact_paths` field, populated by `propose_patch`'s own `artifacts` arg, and the package re-export; nothing reads `execute_code(...).artifact_paths`). The drop is inert.
- **Files modified:** src/agent_mesh/sandbox/executor.py
- **Verification:** grep confirms no reader; `tests/test_sandbox.py` (which does not assert artifacts) passes.
- **Committed in:** 5bebfa1 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes are required for the hardened path to be correct — the mount fix lets the container start at all, and the artifact fix avoids returning misleading state that the RF-4 read-only/tmpfs design makes structurally impossible. No scope creep — the security flag set and contracts are exactly as specified, and no consumer depends on `execute_code`'s artifact discovery. Restoring artifacts would require a writable host bind (`-v <hostdir>:/out:rw`), which is deferred until a downstream consumer needs it.

## Issues Encountered
- **Environment had no `python:3.11-slim` image** — pulled it (`docker pull python:3.11-slim`) so the Docker-gated OOM test could run rather than error. Pull is a one-time runtime prerequisite, not a code change.

## Out-of-Scope (logged to deferred-items.md)
- 8 unrelated test failures (`tests/test_approval_security.py`, `tests/test_importability.py::...app`) fail with `ModuleNotFoundError: No module named 'fastapi'` — the API/approval surface (plans 02-01/02-02), not the sandbox. `tests/test_sandbox.py` is fully green and the sandbox module imports cleanly.
- `make smoke` fails only because the Makefile invokes `python` while this env exposes `python3`; `make smoke` does not touch the sandbox path, and `PYTHONPATH=src python3 -m tests.smoke` reports `SMOKE OK`.

## Threat Flags
None — no security surface beyond the `<threat_model>` already declared in the plan. The change reduces attack surface (closes the fail-open and constrains execution to a hardened container).

## Next Phase Readiness
- SBX-01 satisfied: the sandbox enforces its memory limit without failing open (refuses when Docker absent) and executes via the hardened cgroup container path, with OOM surfacing as exit 137 on the Docker path.
- The prompt-to-code / code-writer roles can now rely on a fail-closed sandbox boundary for downstream E2E plans.

## Self-Check: PASSED
- FOUND: src/agent_mesh/sandbox/executor.py
- FOUND: tests/test_sandbox.py
- FOUND commit: 5bebfa1 (Task 1)
- FOUND commit: a499aed (Task 2)

---
*Phase: 02-real-orchestration-engine*
*Completed: 2026-06-05*
