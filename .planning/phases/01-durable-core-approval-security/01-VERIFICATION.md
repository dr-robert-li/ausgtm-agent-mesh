---
phase: 01-durable-core-approval-security
verified: 2026-06-05T09:19:11Z
status: passed
score: 10/10 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 01: Durable Core & Approval Security — Verification Report

**Phase Goal:** Replace the in-memory store with a durable Postgres-backed repository that survives restarts and enforces tenant isolation, wire runtime dispatch, and close the critical write-gate bypass by authenticating the approval callback.

**Verified:** 2026-06-05T09:19:11Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                                             | Status     | Evidence                                                                                       |
|----|-------------------------------------------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------|
| 1  | After worker restart, queued task resumes from Postgres with no lost state (all 4 DUR-01 families)               | VERIFIED   | `test_restart_survival_all_four_state_families` passed live against pgvector:pg16              |
| 2  | Read scoped to one tenant never returns another tenant's events, approvals, tool-calls, or evaluations            | VERIFIED   | `test_cross_tenant_reads_return_empty` passed live; `AND tenant_id = %s` in all 4 list_* SQL  |
| 3  | POST to `/v1/approvals` without valid signed token rejected (401); forged `approver_id` in body cannot approve    | VERIFIED   | fail-closed `if not secret_val: return None` line 129 approvals.py; 15 security tests pass     |
| 4  | Editing payload after approval invalidates it; approval not replayable across tasks                               | VERIFIED   | `test_mutated_payload_invalidates_approval` + `test_approval_not_replayable_across_tasks` pass |
| 5  | MCP `submit_approval` enforces same HMAC gate as HTTP (no `approver_id` param, token required)                   | VERIFIED   | `submit_approval_decision_with_token` in mcp_server.py; `test_mcp_submit_approval_requires_token` |
| 6  | `GET /v1/tasks/{id}` and MCP `get_task` do not expose approval token in metadata (CR-01)                         | VERIFIED   | `public_task_dict` redacts key; both endpoints call it; 2 dedicated regression tests pass       |
| 7  | In-process dispatcher fallback drains published tasks without cloud dependencies                                   | VERIFIED   | `test_inprocess_fallback_drains` passes unconditionally; 77/77 suite green without emulator    |
| 8  | With `USE_PUBSUB=true` and Pub/Sub emulator, task id published is consumed end-to-end                             | VERIFIED   | `test_pubsub_publish_consume_roundtrip` passed — 2/2 tests passed with emulator live           |
| 9  | `pubsub_setup.py` is idempotent — re-running does not error on AlreadyExists                                      | VERIFIED   | `AlreadyExists` swallowed narrowly for both topic and subscription; emulator test re-run clean  |
| 10 | `get_repository()` routes to `RepositorySQL` when `DATABASE_URL` is set, else `InMemoryRepository`               | VERIFIED   | Lines 836-853 repository.py; `test_round_trip_preserves_fields_and_metadata` confirms SQL path  |

**Score:** 10/10 truths verified

---

### ROADMAP Success Criteria Coverage

| Criterion                                                                                                    | Status   | Evidence                                                                                 |
|--------------------------------------------------------------------------------------------------------------|----------|------------------------------------------------------------------------------------------|
| After worker restart, queued task resumes from Postgres with no lost state                                   | VERIFIED | SQL test `test_restart_survival_all_four_state_families` — live pgvector run, all 4 families |
| Read scoped to one tenant never returns another tenant's events or evaluations                                | VERIFIED | SQL test `test_cross_tenant_reads_return_empty` — list_events/list_approvals/list_tool_calls/list_evaluations all return [] for wrong tenant |
| POST to `/v1/approvals` without valid signed token rejected; forged `approver_id` cannot approve              | VERIFIED | `test_forged_approver_id_rejected`, `test_missing_secret_rejects`, `test_valid_token_accepted` — all pass |
| Editing payload after approval invalidates it; approval not replayable across tasks                           | VERIFIED | `test_mutated_payload_invalidates_approval`, `test_approval_not_replayable_across_tasks` — pass |

---

### Required Artifacts

| Artifact                                              | Expected                                           | Status   | Details                                                                    |
|-------------------------------------------------------|----------------------------------------------------|----------|----------------------------------------------------------------------------|
| `src/agent_mesh/services/repository.py`               | `RepositorySQL` class with psycopg3 pool           | VERIFIED | `class RepositorySQL` at line 454; `_pool: ConnectionPool` field            |
| `src/agent_mesh/services/repository.py`               | `get_repository()` routing function                | VERIFIED | Lines 836-853; returns `RepositorySQL(database_url)` when `DATABASE_URL` set |
| `src/agent_mesh/services/approvals.py`                | `verify_approval_token()` with fail-closed HMAC    | VERIFIED | Lines 113-155; `if not secret_val: return None` at line 129                |
| `src/agent_mesh/services/approvals.py`                | `open_approval()` returns `(record, token)` tuple  | VERIFIED | Lines 160-176; `record, token = approvals.open_approval(...)` in runner.py line 87 |
| `src/agent_mesh/api/serialization.py`                 | `public_task_dict()` strips approval token         | VERIFIED | Lines 21-34; imports `APPROVAL_TOKENS_METADATA_KEY` for single-key-name truth |
| `src/agent_mesh/api/app.py`                           | `/v1/approvals` uses token-derived approver        | VERIFIED | Lines 106-119; `approver_id = approvals.verify_approval_token(...)`; body `approver_id` never used |
| `src/agent_mesh/api/mcp_server.py`                    | `submit_approval` tool has same gate as HTTP       | VERIFIED | `submit_approval_decision_with_token()` function; no `approver_id` param on tool |
| `src/agent_mesh/services/pubsub_setup.py`             | Idempotent topic+subscription creation             | VERIFIED | `AlreadyExists` swallowed for both; lazy google imports                    |
| `src/agent_mesh/worker/dispatcher.py`                 | In-process fallback retained                       | VERIFIED | `test_inprocess_fallback_drains` passes without `USE_PUBSUB`               |
| `migrations/0001_init.sql`                            | Schema for all 4 DUR-01 state families             | VERIFIED | `CREATE TABLE tasks`, `task_events`, `sessions`, `tool_calls` + `approvals` present |
| `tests/test_repository_sql.py`                        | SQL test suite (skips without `TEST_DATABASE_URL`) | VERIFIED | 4 test functions; all 4 passed live against pgvector:pg16                  |
| `tests/test_approval_security.py`                     | 15 security test functions                         | VERIFIED | Confirmed in suite: `test_http_task_read_does_not_leak_approval_token` + `test_public_task_dict_strips_token_without_mutating_record` at lines 307/329 |
| `tests/test_pubsub_dispatch.py`                       | Emulator test (skips without env) + fallback test  | VERIFIED | 2/2 passed with `PUBSUB_EMULATOR_HOST=localhost:8085`; fallback unconditional |

---

### Key Link Verification

| From                           | To                                        | Via                                      | Status   | Details                                                            |
|--------------------------------|-------------------------------------------|------------------------------------------|----------|--------------------------------------------------------------------|
| `runner.py` line 87            | `approvals.open_approval()`               | tuple unpack `record, token =`           | WIRED    | Token stashed to `task.metadata[APPROVAL_TOKENS_METADATA_KEY]`     |
| `runner.py` line 110           | `repo.list_tool_calls(task_id, tenant_id)` | `_pending_calls(task_id, task.tenant_id)` | WIRED    | No direct dict reach-in; grep confirms 0 matches for `_repo._tool_calls` |
| `app.py` GET `/v1/tasks/{id}`  | `public_task_dict(task)`                  | line 51                                  | WIRED    | `return public_task_dict(task)` — CR-01 closed                     |
| `mcp_server.py` `get_task`     | `public_task_dict(task)`                  | line 95                                  | WIRED    | `return public_task_dict(task)` — CR-01 closed both paths          |
| `app.py` `/v1/approvals`       | `approvals.verify_approval_token()`       | lines 110-112                            | WIRED    | 401 on `None`; approver from token not body                        |
| `mcp_server.py` `submit_approval` | `submit_approval_decision_with_token()` | direct call line 108                     | WIRED    | Shares same gate function as HTTP path                             |
| `RepositorySQL.list_events()`  | `AND tenant_id = %s`                      | line 597 repository.py                   | WIRED    | Parameterized; no f-string interpolation with runtime values       |
| `RepositorySQL.list_tool_calls()` | `AND tenant_id = %s`                   | line 646                                 | WIRED    | Confirmed                                                          |
| `RepositorySQL.list_approvals()` | `AND tenant_id = %s`                    | line 691                                 | WIRED    | Confirmed                                                          |
| `RepositorySQL.list_evaluations()` | `AND tenant_id = %s`                  | line 787                                 | WIRED    | Confirmed                                                          |
| `RepositorySQL.transition_task()` | atomic UPDATE + INSERT                 | single `with self._pool.connection() as conn:` block lines 545-571 | WIRED | Pitfall 7 closed |

---

### Data-Flow Trace (Level 4)

| Artifact                    | Data Variable            | Source                                    | Produces Real Data | Status  |
|-----------------------------|--------------------------|-------------------------------------------|--------------------|---------|
| `RepositorySQL.get_task()`  | task row                 | `SELECT … FROM tasks WHERE task_id = %s`  | Yes — DB query     | FLOWING |
| `RepositorySQL.list_events()` | event rows             | `SELECT … FROM task_events WHERE … AND tenant_id = %s` | Yes — DB query | FLOWING |
| `public_task_dict(task)`    | `metadata` dict          | `task.model_dump(mode="json")`            | Yes — real record; redacts token key | FLOWING |
| `verify_approval_token()`   | `approver_id`            | HMAC-SHA256 verify against stored `signing_secret` | Yes — stdlib hmac | FLOWING |

---

### Behavioral Spot-Checks

| Behavior                                         | Command                                                                                  | Result         | Status |
|--------------------------------------------------|------------------------------------------------------------------------------------------|----------------|--------|
| All 4 DUR-01 state families survive pool restart | `pytest tests/test_repository_sql.py::test_restart_survival_all_four_state_families -v` | PASSED (live)  | PASS   |
| Cross-tenant list_* returns []                   | `pytest tests/test_repository_sql.py::test_cross_tenant_reads_return_empty -v`          | PASSED (live)  | PASS   |
| Forged approver_id rejected 401                  | `pytest tests/test_approval_security.py::test_forged_approver_id_rejected -v`           | PASSED         | PASS   |
| Missing secret fail-closed                       | `pytest tests/test_approval_security.py::test_missing_secret_rejects -v`                | PASSED         | PASS   |
| Token-stripped task read (CR-01)                 | `pytest tests/test_approval_security.py::test_http_task_read_does_not_leak_approval_token -v` | PASSED    | PASS   |
| Pub/Sub emulator publish→consume                 | `PUBSUB_EMULATOR_HOST=localhost:8085 pytest tests/test_pubsub_dispatch.py -v`            | 2/2 PASSED     | PASS   |
| In-process fallback drains                       | `pytest tests/test_pubsub_dispatch.py::test_inprocess_fallback_drains -v`               | PASSED         | PASS   |
| Full suite                                       | `pytest --tb=no -q`                                                                      | 77 passed, 5 skipped (emulator absent) | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                              | Status    | Evidence                                                       |
|-------------|-------------|----------------------------------------------------------|-----------|----------------------------------------------------------------|
| DUR-01      | 01-01-PLAN  | Postgres-backed repository; 4 state families persist     | SATISFIED | `RepositorySQL` + `test_restart_survival_all_four_state_families` (live) |
| DUR-02      | 01-01-PLAN  | Tenant isolation on `list_*` read paths                  | SATISFIED | `AND tenant_id = %s` in all 4 list_* methods; SQL test passes  |
| DUR-03      | 01-02-PLAN  | Pub/Sub dispatch wired; in-process fallback retained     | SATISFIED | Both emulator test (2/2 live) + fallback test pass             |
| SEC-01      | 01-03-PLAN  | HMAC token gate on `/v1/approvals` + MCP; fail-closed    | SATISFIED | `verify_approval_token` fail-closed; both paths share one gate; 15 tests |
| SEC-02      | 01-03-PLAN  | Payload mutation invalidates; cross-task replay blocked  | SATISFIED | `is_approved` re-hashes; `record_id` bound in token; 2 targeted tests   |

**Note on WR-01 (accepted scope decision):** `get_*` single-entity reads in `RepositorySQL` use PK only and are not tenant-scoped. Plan 01-01 deliberately narrowed DUR-02 to `list_*` paths. This is a documented, accepted decision recorded in `deferred-items.md` — not a gap. Defense-in-depth hardening of `get_*` is tracked for a later phase.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `worker/runner.py` | 129 | `_resume_after_approval` unconditionally transitions to COMPLETED (CR-02) | Info | Latent only; current stub emits at most one write. Risk activates in Phase 2 when orchestrator emits >1 gated writes. Documented in deferred-items.md. |
| `services/approvals.py` | — | Token replay within TTL not checked (WR-02, no nonce/consumed flag) | Info | Deferred. Bounded by short token TTL. Documented in deferred-items.md. |
| `api/app.py` | — | Invalid `decision` value → 500 not 400 (WR-03) | Info | Deferred quality item. No security impact. |

No `TBD`, `FIXME`, or `XXX` markers found in phase-modified files. No stub components (empty return null / placeholder divs) — this is a Python backend. No hardcoded empty data flowing to output paths.

---

### Human Verification Required

None. All truths verified programmatically including the Pub/Sub emulator path (confirmed live with `docker run google/cloud-sdk` + `PUBSUB_EMULATOR_HOST=localhost:8085`).

---

### Gaps Summary

No gaps. All 10 truths verified. All 4 ROADMAP success criteria met. All 5 requirement IDs (DUR-01, DUR-02, DUR-03, SEC-01, SEC-02) satisfied.

The one accepted scope carve-out (WR-01 — `get_*` single-entity reads not tenant-scoped) is a documented, intentional decision in `deferred-items.md`, not a phase gap.

---

_Verified: 2026-06-05T09:19:11Z_
_Verifier: Claude (gsd-verifier)_
