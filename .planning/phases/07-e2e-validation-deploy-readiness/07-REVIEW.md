---
phase: 07-e2e-validation-deploy-readiness
reviewed: 2026-06-08T09:15:00+10:00
depth: standard
files_reviewed: 11
files_reviewed_list:
  - tests/e2e/test_e2e_slack_write_gated.py
  - tests/e2e/test_e2e_slack_write_gated_live.py
  - tests/e2e/test_e2e_mcp_durable_job.py
  - tests/e2e/test_e2e_mcp_durable_job_live.py
  - tests/e2e/test_e2e_failure_modes.py
  - tests/e2e/test_e2e_failure_modes_live.py
  - tests/deploy/test_gcloud_idempotency.py
  - tests/deploy/test_manifest_consistency.py
  - tests/deploy/bin/gcloud
  - tests/deploy/bin/wrangler
  - scripts/gcp_bootstrap.sh
  - scripts/gcp_deploy_core.sh
  - scripts/cf_deploy_ai_gateway_worker.sh
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
findings_original:
  critical: 1
  warning: 4
  info: 2
  total: 7
resolved_by_07_05: [CR-01, WR-01, WR-02]
status: issues_found
status_note: >
  CR-01 (critical), WR-01, WR-02 closed by gap-closure plan 07-05 (verified test-side,
  production unchanged). Remaining advisory findings WR-03/WR-04 (07-04/07-01 files) and
  IN-01/IN-02 (07-03 files) are OUT OF 07-05 SCOPE and non-blocking.
---

# Phase 07: Code Review Report

## Gap-closure 07-05 resolutions (2026-06-08T11:08:00Z)

Plan 07-05 closed the three findings against the E2E-02 modules. All test-side; `git diff
--stat src/` is empty (production `_graph_config` unchanged).

| Finding | Resolution | Evidence |
|---------|-----------|----------|
| **CR-01** (critical) | Default-lane test now drives the production `Worker.process -> run_mesh -> _run_langgraph -> _select_checkpointer -> _graph_config` path via the `set_checkpointer_override` seam, on the BARE production key; `tenant-t::` invention and false DUR-02 docstring removed; discriminating reopened-checkpoint reads (survival + consumption) go red on checkpoint loss. | `grep tenant-t:: == 0`; `get_tuple(cfg) >= 2`; `build_graph().compile == 0`; test PASSES (not skips). |
| **WR-01** (warning) | `test_e2e_mcp_transport_create_task` now invokes the registered FastMCP tool via `await server.call_tool("create_task", ...)` and reads the task back through the shared `TaskService`; construction-only assertion removed. | `grep call_tool >= 1`; `grep "server is not None" == 0`; test passes. |
| **WR-02** (warning) | Postgres lane gains the `saver2 is not saver` post-close negative assertion + bare-key `_graph_config`; `make test-pg` + RUNBOOK note make the DSN-gated lane runnable on deploy-readiness (loud-skip when unset). | `grep "saver2 is not saver" == 1`; `test-pg` in Makefile; `TEST_DATABASE_URL` in RUNBOOK. |

**Remaining (out of 07-05 scope, advisory):** WR-03 (deploy idempotency direction coverage,
`07-04`), WR-04 (`_tasks` private access in `07-01` slack test), IN-01/IN-02 (`07-03`
failure-modes assertions). Non-blocking; tracked for a future polish pass.

---

# Phase 07: Code Review Report (original)

**Reviewed:** 2026-06-08T09:15:00+10:00
**Depth:** standard
**Files Reviewed:** 11 source files + 3 deploy scripts (cross-referenced)
**Status:** issues_found

## Summary

Phase 07 adds test-only and deploy-shim-only code: six E2E test modules, two deploy test
modules, two PATH-shim binaries, and three bash deploy scripts. No product code is added.

The four priority axes were:

1. **Test validity / false-positive risk** — one critical finding (thread_id divergence in
   E2E-02 means the durability proof is tautological on its own design convention, not the
   production path).
2. **Live-lane gating** — all live lanes skip loudly without creds; `live_creds` fixture
   skips (not dummy-creds); `pytestmark = pytest.mark.live` is module-level for every
   live file except the DSN-gated Postgres lane (correct by design).
3. **Bash shim correctness** — shims are sound for their declared scope; no exit-code
   leaks under `set -euo pipefail`.
4. **Standard bugs / security / quality** — no injection risks; private attribute access
   is a brittleness warning; one idempotency-direction gap confirmed.

The E2E-01 chain (SP-1 rebind, 4-leg HTTP proof), E2E-03 Stage B (singleton-pinned +
`_boom`-guarded budget halt via production `Worker.process`), and all deploy manifest
consistency checks are well-constructed and prove what they claim.

---

## Critical Issues

### CR-01: E2E-02 thread_id diverges from production — durability proof is tautological

**File:** `tests/e2e/test_e2e_mcp_durable_job.py:91` and
`tests/e2e/test_e2e_mcp_durable_job_live.py:92`

**Issue:** Both E2E-02 modules manually construct the checkpoint key as:
```python
thread_id = f"tenant-t::{task.task_id}"
```
Production `orchestrator._graph_config()` (line 319) constructs it as:
```python
config: dict = {"configurable": {"thread_id": task.task_id}}
```
The test uses a `tenant-t::` prefix that does not exist in production. The sqlite
drop-and-reopen restart proof works end-to-end because both `graph.invoke(paused)` and
`graph2.invoke(Command(resume=True))` use the same manually-constructed key — but that
key is the test's own invention, not what production would write. If a real `Worker`
paused the graph using `_graph_config(task)` (bare `task.task_id`), a restart resuming
with the tenant-prefixed key would read an empty checkpoint and either error or start a
new run — not resume.

The live Postgres variant (`test_e2e_postgres_durable_restart`) also constructs the same
divergent key and routes through `orchestrator._select_checkpointer()` / `close_checkpointer()`
for the saver lifecycle, but still bypasses `orchestrator._graph_config()` for the key.
The DUR-02 comment in both files claims "the resume always keys on `thread_id == the
tenant-scoped task_id` (`tenant-t::` form)" but this form is asserted only in the test,
never enforced in production.

Two possible fixes (choose one):

**Option A — fix production `_graph_config` to use the tenant-scoped form (preferred):**
```python
# orchestrator.py _graph_config
config: dict = {
    "configurable": {
        "thread_id": f"{task.tenant_id}::{task.task_id}"
    }
}
```
Then update tests to call `_graph_config(task)` directly instead of constructing the
key inline, so the test always tracks the production form.

**Option B — fix tests to call `_graph_config` (minimal change, doesn't fix DUR-02):**
```python
# In test body, after task = svc.create_task(...)
from agent_mesh.worker.orchestrator import _graph_config
config = _graph_config(task)
```
This removes the divergence but leaves production still using a bare key (no DUR-02
cross-task isolation at the checkpointer level).

---

## Warnings

### WR-01: MCP-transport test proves server construction, not the registered tool

**File:** `tests/e2e/test_e2e_mcp_durable_job_live.py:121-153`

**Issue:** `test_e2e_mcp_transport_create_task` asserts `server is not None` (FastMCP
constructed), then calls `svc.create_task(request_from_mcp(...))` **directly** — never
through the MCP server's registered `create_task` tool. The docstring claims it "proves
the MCP-transport `create_task` tool funnels into the same shared TaskService" but the
tool registration itself is never invoked. A broken or misrouted tool registered on
`server` would not cause this test to fail.

**Fix:** Either scope the claim honestly (rename to `test_e2e_mcp_server_construction`
and remove the "funnels into" assertion), or drive the tool through the FastMCP test
client:
```python
# Use FastMCP's in-process test client to actually invoke the registered tool
from mcp.test import MCPTestClient  # or equivalent FastMCP harness
with MCPTestClient(server) as client:
    result = client.call_tool("create_task", {"text": "summarize notes", ...})
    task_id = result["task_id"]
    fetched = svc.get_task(task_id)
    assert fetched is not None
```

### WR-02: Postgres restart test never executed — skipped in every documented run

**File:** `tests/e2e/test_e2e_mcp_durable_job_live.py:53-118`

**Issue:** `test_e2e_postgres_durable_restart` is gated on `pg_dsn` (requires
`TEST_DATABASE_URL`) and `_backend_available("langgraph.checkpoint.postgres")`. The
07-02-SUMMARY confirms `TEST_DATABASE_URL` was unset in every validation environment,
so this test was always skipped. The saver-lifecycle and connection-caching assertions
(`saver2 is saver`) are latent code that has never run against a real Postgres
checkpointer in this phase. The headline durability claim rests entirely on the sqlite
default lane.

Additionally, there is a subtle assertion risk: `assert orchestrator._select_checkpointer()
is saver` (line 100) verifies connection caching before the restart. After
`close_checkpointer()`, `saver2 = orchestrator._select_checkpointer()` constructs a new
object. The test asserts `saver2 is not None` but does NOT assert `saver2 is not saver`
(line 109-110), leaving the post-close fresh-construction guarantee unverified.

**Fix:**
1. Add CI step that sets `TEST_DATABASE_URL` against a local Postgres (testcontainers
   or Docker Compose) so this lane runs at least on the deploy-readiness validation.
2. Add the missing negative assertion:
```python
orchestrator.close_checkpointer()
saver2 = orchestrator._select_checkpointer()
assert saver2 is not saver, "close_checkpointer must drop cache; new saver expected"
assert saver2 is not None
```

### WR-03: Asymmetric idempotency direction coverage in deploy tests

**File:** `tests/deploy/test_gcloud_idempotency.py`

**Issue:** Two idempotency directions are not covered:

- **Service-account create-when-absent:** only the reuse (exists) direction is tested.
  `gcp_bootstrap.sh` line 102 uses `gcloud iam service-accounts describe ... || create`,
  but no test exercises the ABSENT path (shim flips describe to exit 1, create fires).
- **Cloud SQL instance reuse-when-exists:** only the ABSENT (create) direction is tested.
  `gcp_bootstrap.sh` lines 130-141 use `if ! gcloud sql instances describe ...` / `else
  reusing`, but no test exercises the EXISTS path (shim returns success, create is skipped).

The ABSENT-only SQL test is also fragile: the test asserts `"sql instances create" in log`
but never asserts the create command receives the expected flags (`--database-version`,
`--availability-type`, etc.). A bootstrap that runs an empty `gcloud sql instances create`
would pass the test.

**Fix:** Add the two missing direction tests:
```python
def test_service_account_create_when_absent(tmp_path, monkeypatch):
    shim_log, run = _make_shim_env(tmp_path, monkeypatch, absent_pattern="describe")
    result = run(["gcp_bootstrap.sh"])
    assert result.returncode == 0
    log = shim_log.read_text()
    assert "service-accounts create" in log  # at least one SA creation fired

def test_cloud_sql_instance_reuse_when_exists(tmp_path, monkeypatch):
    shim_log, run = _make_shim_env(tmp_path, monkeypatch, absent_pattern=None)  # describe succeeds
    result = run(["gcp_bootstrap.sh"])
    assert result.returncode == 0
    log = shim_log.read_text()
    assert "sql instances create" not in log   # reuse branch taken, no create
    assert "sql instances describe" in log
```

### WR-04: `_tasks` private attribute access in E2E-01 couples test to implementation detail

**File:** `tests/e2e/test_e2e_slack_write_gated.py` (task extraction from `repo._tasks`)

**Issue:** The test extracts the created task via:
```python
task = next(iter(repo._tasks.values()))
assert len(repo._tasks) == 1
```
`_tasks` is a private attribute of `InMemoryRepository`. If the repository implementation
renames or restructures the backing store (e.g. moves to `_store`, wraps in a
`collections.OrderedDict` with a different key scheme), this test breaks with an
`AttributeError` rather than a meaningful assertion failure. The same test also reads
`repo.get_task(task_id).metadata["approval_tokens"]` with no None guard — if `get_task`
returns None (task creation failed silently), the subsequent `.metadata` access raises
`AttributeError` masking the real failure.

**Fix:**
```python
# Replace private access with public API
all_tasks = repo.list_tasks(tenant_id=task_tenant_id)
assert len(all_tasks) == 1
task = all_tasks[0]

# Add None guard on get_task
task_record = repo.get_task(task_id)
assert task_record is not None, "task must exist after APPROVED transition"
tokens = task_record.metadata.get("approval_tokens", [])
assert tokens, "worker must have issued at least one approval token"
```

---

## Info

### IN-01: E2E-03 Stage A proves cascade configuration, not mid-run provider failure

**File:** `tests/e2e/test_e2e_failure_modes.py:87-101`

**Issue:** Stage A uses `mock_testing_fallbacks=True` which forces litellm's internal
`InternalServerError` path — this proves that the **configuration** correctly maps
`low-complexity -> gemini-1.5-pro` fallback, not that a real provider failure triggers
the cascade at runtime. The test docstring calls this "in-cascade retry-recovery" which
is technically accurate but the live lane owns the real-provider-error proof. Anyone
reading the default-lane test in isolation may overestimate what is proven. No code
change needed, but the distinction should be preserved in documentation.

### IN-02: `resp.model` assertion in E2E-03 Stage A is configuration-name fragile

**File:** `tests/e2e/test_e2e_failure_modes.py:97-101`

**Issue:** The assertion `assert resp.model == _FALLBACK_MODEL` where `_FALLBACK_MODEL =
"gemini-1.5-pro"` relies on litellm returning the canonical model name string, not the
deployment name or a variant. litellm's `ModelResponse.model` field reflects what the
provider returns (or the litellm normalized name), which can differ from the configured
deployment name across litellm versions. If litellm changes normalization (e.g. to
`"gemini/gemini-1.5-pro"` or `"vertex_ai/gemini-1.5-pro"`), the test fails with no
production defect.

**Fix:** Loosen the assertion to a substring check consistent with how the live lane
checks the Anthropic model:
```python
assert "gemini-1.5-pro" in (resp.model or ""), (
    f"expected fallback model to contain 'gemini-1.5-pro', got {resp.model!r}"
)
```

---

_Reviewed: 2026-06-08T09:15:00+10:00_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
