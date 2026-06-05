---
phase: 01-durable-core-approval-security
plan: 03
subsystem: approval-gate / security
tags: [SEC-01, SEC-02, hmac, approval-token, fail-closed, replay-defense]
requires:
  - "01-01: widened Repository protocol (list_tool_calls/list_approvals + tenant_id) and repaired resume path"
provides:
  - "issue_approval_token / verify_approval_token (stdlib HMAC, fail-closed) binding approval_record_id|payload_hash|requester_id|exp"
  - "open_approval now returns (record, token); worker stashes the token on task metadata"
  - "Fail-closed token enforcement at /v1/approvals AND the MCP submit_approval tool; approver derived from token, body value ignored"
  - "mcp_server.submit_approval_decision_with_token: directly-testable shared MCP-path gate"
  - "settings.approval_signing_secret_env + .env.example APPROVAL_SIGNING_SECRET (fail-closed note)"
affects:
  - "Every gated write: open_approval is the single issuance point; both ingress callbacks now require a verified token"
tech-stack:
  added: []
  patterns:
    - "stdlib hmac/hashlib/time only (no new packages); hmac.compare_digest constant-time compare"
    - "fail-closed verify (returns None with no secret) — deliberate divergence from slack_verify's dev fail-open"
    - "token bound per approval record (cross-task replay rejected); exp claim bounds the leakage window"
    - "shared module-level gate reused by HTTP + MCP so the bypass cannot reopen on one path"
key-files:
  created:
    - tests/test_approval_security.py
  modified:
    - src/agent_mesh/services/approvals.py
    - src/agent_mesh/settings.py
    - src/agent_mesh/worker/runner.py
    - src/agent_mesh/services/self_improvement.py
    - src/agent_mesh/api/app.py
    - src/agent_mesh/api/mcp_server.py
    - .env.example
decisions:
  - "issue_approval_token NEVER raises with no secret (signs with empty string -> unverifiable); fail-closed lives entirely in verify, so the existing no-secret gating/self-improvement/smoke pause paths keep working"
  - "no model change: the worker carries the issued token on TaskRecord.metadata['approval_tokens'][record_id] (round-trips via Wave 1's task_metadata); real-time Slack/MCP token DELIVERY is deferred (scaffold has no postback channel)"
  - "self_improvement promotion path unpacks (record, _token) and defers delivery (no ingress delivers it this phase) — only point of the touch is to avoid a tuple TypeError"
  - "MCP gate extracted to module-level submit_approval_decision_with_token in mcp_server.py (NOT app.py, which imports FastAPI at top and would break mcp_server's minimal-env importability); satisfies one-shared-gate by construction"
  - "token parse uses rsplit('.',2) then split('.',1) so a dotted requester (e.g. mcp:sub.x) cannot break parsing"
metrics:
  duration: ~40m
  completed: 2026-06-05
  tasks: 3
  files: 7
---

# Phase 1 Plan 03: HMAC Approval Token (Fail-Closed) Summary

Closed the Critical write-gate bypass (CONCERNS.md #1): `/v1/approvals` and the MCP `submit_approval` tool previously recorded a self-asserted `approver_id` with no signature. Added a stdlib-HMAC approval token issued when an approval opens (`open_approval` now returns `(record, token)`), verified **fail-closed** at both ingress points, with the recorded approver derived from the verified token and the request body value ignored — plus the full SEC-01/SEC-02 test suite (forgery, replay, payload-mutation, expiry, fail-closed, MCP parity).

## What Was Built

- **Task 1 (linchpin, `670e58c`, TDD)** — `approvals.issue_approval_token` / `verify_approval_token` using stdlib `hmac`/`hashlib`/`time`, mirroring `slack_verify`'s `hmac.new(...).hexdigest()` + `hmac.compare_digest`. Token format `{record_id}.{requester_id}.{exp}.{sig}` where `sig = HMAC-SHA256(secret, "{record_id}:{payload_hash}:{requester_id}:{exp}")`, default TTL 3600s. `verify` FAILS CLOSED (returns `None`) when `APPROVAL_SIGNING_SECRET` is unset, and on malformed token / record-id mismatch (cross-task replay) / expiry / HMAC mismatch; it returns the token's `requester_id` (the only trusted approver). `open_approval` now returns `(record, token)`; the worker unpacks it and stashes the token on `TaskRecord.metadata['approval_tokens'][record_id]`; `self_improvement` unpacks `(record, _token)` with a deferred-delivery note. Added `settings.approval_signing_secret_env` and the `.env.example` entry. Token-unit tests (valid/missing-secret/tampered/expired/cross-record) pass.
- **Task 2 (`fbedb6f`)** — Enforced the token at both ingress points. `/v1/approvals` loads the record (404 if unknown), `verify_approval_token` (401 if `None`), passes the **token-derived** `approver_id` into `submit_approval_decision`, and ignores any body `approver_id`. Extracted `submit_approval_decision_with_token` as a module-level helper in `mcp_server.py` (directly testable, importable in minimal envs); the `submit_approval` tool drops `approver_id`, adds an `approval_token` param, and calls the shared gate. One gate, both paths (Pitfall 4).
- **Task 3 (`f125405`, TDD)** — Finalized `tests/test_approval_security.py` (13 behaviors): valid-token-accepted, forged-approver-rejected (no-token 401 + valid-token records token's requester not the spoofed body), missing-secret-rejects (fail-closed), tampered/expired token, cross-task replay, payload-mutation-invalidates-approval (worker resume path / SEC-02a), and MCP parity. Positive cases set `APPROVAL_SIGNING_SECRET`; the token is read back from the worker's live `open_approval` stash (not hand-minted).

## Verification Evidence

- Full suite (venv with fastapi/mcp/pytest installed): **75 passed, 5 skipped** (SQL + emulator tests skip on unset `TEST_DATABASE_URL` / `PUBSUB_EMULATOR_HOST`). `tests/test_approval_security.py` alone: **13 passed**.
- `make smoke` equivalent → `SMOKE OK` (write task pauses→approved→completed; read task completes without approval). The smoke path runs `open_approval` with NO secret, proving issuance is non-throwing.
- Existing `test_approval_gating.py` + `test_self_improvement.py` (run WITHOUT a secret): **18 passed** — confirms the `(record, token)` tuple change and on-every-pause issuance did not regress the no-secret paths (advisor landmine #1).
- ruff: clean on all changed source + test files.
- Source assertions: `if not secret_val: return None` before any compare (approvals.py:120); `hmac.compare_digest` not `==` (approvals.py:144); `approval_signing_secret_env = "APPROVAL_SIGNING_SECRET"` (settings.py:85); both ingress points derive `approver_id` only from `verify_approval_token` (app.py:109/116, mcp_server.py:43/50).

## Deviations from Plan

### Auto-fixed Issues

None — all three tasks executed as written. The plan explicitly resolved the under-specified "attach the token" seam by deferring real-time delivery; the chosen no-model-change home (`TaskRecord.metadata`) is within `files_modified` (no `models.py` edit) and round-trips via Wave 1's `task_metadata` persistence.

### Test-environment setup (not a code deviation)

- `fastapi`/`mcp`/`pytest` were not present on the worktree interpreter (the Wave 1 deferred-items note recorded this). Created a throwaway venv (`/tmp/wt03venv`) and `pip install -e .` + `-r requirements/dev.txt` to run the HTTP/MCP TestClient paths. These are already-declared dependencies (pyproject `fastapi>=0.110`, runtime extra `mcp>=1.2`), not package substitutions. No repository dependency files were changed.

## Threat Model Disposition

| Threat ID | Disposition | Evidence |
|-----------|-------------|----------|
| T-03-01 (spoofed approver / EoP) | mitigated | approver derived from verified token at HTTP AND MCP; `test_forged_approver_id_rejected` + `test_mcp_submit_approval_requires_token` pass |
| T-03-02 (cross-task replay) | mitigated | token bound to `approval_record_id`; verify rejects on record-id mismatch; `test_approval_not_replayable_across_tasks` + `test_token_cross_record_returns_none` pass |
| T-03-03 (payload mutation post-approval) | mitigated | existing `is_approved` re-hashes `payload_hash`; `test_mutated_payload_invalidates_approval` asserts the write does NOT execute |
| T-03-04 (fail-open regression) | mitigated | `verify` returns `None` with no secret; `test_missing_secret_rejects` passes |
| T-03-05 (token expiry/leakage) | mitigated | `exp` claim (default 3600s); `test_expired_token_rejected` passes |
| T-03-06 (timing attack) | mitigated | `hmac.compare_digest` constant-time (source assertion approvals.py:144) |
| T-03-07 (forged/unauthenticated POST) | mitigated | verify at both ingress; 401 + no ledger mutation; `test_tampered_token_rejected` / forged tests pass |
| T-03-SC (supply chain) | accepted | no new packages — stdlib hmac/hashlib/time only |

No new threat surface introduced beyond the plan's `<threat_model>`.

## Known Stubs / Deferred

- **Token delivery (deferred by plan):** the scaffold has no Slack/MCP postback channel, so the worker stashes the issued token on task metadata rather than pushing it to the requester. The approval callback presents the token; real-time delivery is a later phase. The self-improvement promotion path discards its token (`_token`) for the same reason. Both are documented in-code and were explicitly scoped out by the plan (`<interfaces>` / Task 1 action).
- **Pre-existing env gap (unchanged from Wave 1):** without a venv, `tests/test_importability.py::test_module_imports[agent_mesh.api.app]` fails because `fastapi` is not installed on the bare interpreter. Resolved by `make install` (or the venv used here). Not a 01-03 regression.

## Self-Check: PASSED
- FOUND: src/agent_mesh/services/approvals.py (`def verify_approval_token`)
- FOUND: tests/test_approval_security.py (`APPROVAL_SIGNING_SECRET`)
- FOUND: src/agent_mesh/api/mcp_server.py (`submit_approval_decision_with_token`)
- FOUND commit 670e58c (Task 1)
- FOUND commit fbedb6f (Task 2)
- FOUND commit f125405 (Task 3)
