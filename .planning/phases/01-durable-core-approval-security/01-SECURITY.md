---
phase: 01
slug: durable-core-approval-security
status: secured
threats_total: 15
threats_closed: 15
threats_open: 0
accepted_risks: 3
asvs_level: 1
auditor: gsd-security-auditor (claude-sonnet-4-6)
created: 2026-06-05
---

# Security Audit — Phase 01: Durable Core & Approval Security

**Audit Date:** 2026-06-05
**Phase:** 01 — durable-core-approval-security
**ASVS Level:** 1 (POC)
**Block On:** critical-or-high open threats
**Auditor:** gsd-security-auditor (claude-sonnet-4-6)
**Verdict:** SECURED — 0 blockers

---

## Threat Verification

All 15 threats in the Phase 01 register verified. 12 `mitigate` dispositions confirmed
by grep match in cited implementation files. 3 `accept` dispositions confirmed by
documented rationale in deferred-items.md and the accepted-risks log below.

| Threat ID | Category | Disposition | Evidence |
|-----------|----------|-------------|----------|
| T-01-01 | Cross-tenant info disclosure (list paths) | mitigate | `repository.py:597,646,691,787` — `AND tenant_id = %s` in all four `list_*` SQL methods; cross-tenant test passes. See WR-01 residual note below. |
| T-01-02 | SQL injection | mitigate | `repository.py` — f-strings embed only static `_*_COLS` constants (lines 421-447); all runtime value bindings use `%s` psycopg3 parameterization |
| T-01-03 | Non-atomic task transition (partial write) | mitigate | `repository.py:559-568` — `transition_task` executes UPDATE + INSERT inside a single `with self._pool.connection() as conn:` block |
| T-01-04 | Private-dict reach-in from outside repository | mitigate | Grep confirms zero `_approvals`/`_tool_calls` access outside `repository.py`; `runner.py:137` and all tests use protocol methods `list_tool_calls`/`list_approvals` |
| T-01-05 | DATABASE_URL absent at startup | accept | Documented accepted risk: in-memory fallback activates; explicit operator runbook note (see accepted-risks log) |
| T-02-01 | Pub/Sub poison-message loop | mitigate | `worker/main.py:40` — `message.nack()` on exception in worker callback |
| T-02-02 | Non-idempotent Pub/Sub topic/subscription setup | mitigate | `pubsub_setup.py:55,60` — `except AlreadyExists: pass` narrow catch on both topic and subscription creation |
| T-02-03 | Sensitive data in Pub/Sub message payload | accept | `dispatch.py:48` — payload is `{"task_id": task_id}` only; no prompt, no PII. Confirmed by grep this session. Documented accepted risk. |
| T-03-01 | Approval bypass — self-asserted approver_id | mitigate | `app.py:110-112` — `approver_id = approvals.verify_approval_token(...)`; 401 on None; body `approver_id` ignored. `mcp_server.py:44-46` — identical gate via `submit_approval_decision_with_token` |
| T-03-02 | Cross-task token replay | mitigate | `approvals.py:138` — `if record_id != record.approval_record_id: return None` |
| T-03-03 | Token expiry not enforced | mitigate | `approvals.py:144` — expiry check against `exp` claim |
| T-03-04 | Fail-open when signing secret absent | mitigate | `approvals.py:129` — `if not secret_val: return None` (fail-closed, not fail-open) |
| T-03-05 | Timing-oracle signature comparison | mitigate | `approvals.py:153` — `hmac.compare_digest(expected, sig)` |
| T-03-06 | Post-approval payload mutation bypasses write gate | mitigate | `approvals.py` — `is_approved` re-hashes `payload_hash` at execution time (called in `runner.py:116`) |
| T-03-SC | Information disclosure — approval token leaked via task-read | mitigate | CR-01 fix: `api/serialization.py:public_task_dict` strips `APPROVAL_TOKENS_METADATA_KEY` from metadata before serialization. Both `app.py:51` (`GET /v1/tasks/{id}`) and `mcp_server.py:95` (MCP `get_task`) route exclusively through this chokepoint. No other `model_dump` calls on task records in the API layer. Durable store retention confirmed: `tests/test_approval_security.py::test_http_task_read_does_not_leak_approval_token` asserts the token is absent from the HTTP response AND present in `repo.get_task(...).metadata["approval_tokens"]`. |

---

## Test Runs (This Session)

| Suite | Result |
|-------|--------|
| `tests/test_approval_security.py` | 15 passed (SEC-01, SEC-02, CR-01 regression) |

---

## Unregistered Flags

No unregistered flags. SUMMARY.md `## Threat Flags` entries for all three plans map
to declared threat IDs (T-01-SC maps to T-03-SC; T-02-01/T-02-02/T-02-03 explicit;
T-03-01 through T-03-06 explicit). No new attack surface appeared without a threat
mapping.

---

## Accepted Risks Log

### AR-01: In-memory repository fallback (T-01-05)

**Threat:** T-01-05 — `DATABASE_URL` absent at startup silently activates in-memory
repository, losing durability.

**Rationale:** POC/local-dev design intent; Cloud Run deployment will always supply
`DATABASE_URL` via Secret Manager. No data-loss risk in production deployment path.

**Condition to close:** Enforce `DATABASE_URL` required at startup before production
deployment (Phase 4 / deploy-readiness hardening).

---

### AR-02: Pub/Sub payload contains only task_id (T-02-03)

**Threat:** T-02-03 — Pub/Sub message payload could expose sensitive task content.

**Rationale:** `dispatch.py:48` publishes `{"task_id": task_id}` only. Worker
re-fetches full task from the database. No prompt, requester PII, or tool parameters
transit Pub/Sub. No mitigation required.

**Condition to close:** Not applicable; design is correct. Re-verify if dispatch.py
payload is ever expanded.

---

### AR-03: Single-entity get_* reads not tenant-scoped (WR-01)

**Threat:** Caller holding another tenant's UUID primary key can read that record
cross-tenant via `get_task`, `get_approval`, `get_tool_call`, etc.

**Rationale:** Plan 01-01 explicitly narrowed DUR-02 tenant-scoping to the `list_*`
paths (PLAN lines 65-67). The `get_*` methods accept globally-unique `uuid4` PKs and
the Repository protocol signatures do not include `tenant_id`. UUID4 keys are
computationally unguessable from outside a tenant boundary; exploitation requires
prior knowledge of another tenant's record ID. Severity: Low for POC with 5 users
and no adversarial cross-tenant threat model.

**Condition to close:** Extend Repository protocol to accept `tenant_id` on all
`get_*` methods and add `AND tenant_id = %s` predicates. Candidate: Phase 2 security
hardening sweep. This note records the REQUIREMENTS "All repository read paths" vs.
plan-scoped "list_* paths" narrowing explicitly so it is a documented decision, not
a silent gap.

---

## Deferred / Latent Items (Non-Blocking)

These items were triaged by the Phase 01 orchestrator (see `deferred-items.md`) and
are NOT open declared threats. None meet the `block_on: critical-or-high` threshold
for this audit.

| Item | Description | Deferred To |
|------|-------------|-------------|
| CR-02 | `_resume_after_approval` unconditionally transitions to COMPLETED regardless of remaining AWAITING_APPROVAL calls. Latent: current stub emits at most 1 write. Risk becomes real when Phase 2 orchestrator emits >1 gated write per run. | Phase 2 |
| WR-02 | Approval token replay within TTL window (no nonce/consumed flag) | Follow-up hardening |
| WR-03 | Invalid `decision` value returns 500 instead of 400 | Follow-up hardening |
| WR-04 | Post-commit task re-read in `submit_approval_decision` outside transaction | Follow-up hardening |
| IN-01 | `_pending_calls` name is misleading (returns all tool calls, not just pending) | Follow-up quality |

---

## Files Audited

- `.planning/phases/01-durable-core-approval-security/01-01-PLAN.md`
- `.planning/phases/01-durable-core-approval-security/01-02-PLAN.md`
- `.planning/phases/01-durable-core-approval-security/01-03-PLAN.md`
- `.planning/phases/01-durable-core-approval-security/01-01-SUMMARY.md`
- `.planning/phases/01-durable-core-approval-security/01-02-SUMMARY.md`
- `.planning/phases/01-durable-core-approval-security/01-03-SUMMARY.md`
- `.planning/phases/01-durable-core-approval-security/01-REVIEW.md`
- `.planning/phases/01-durable-core-approval-security/deferred-items.md`
- `src/agent_mesh/services/approvals.py`
- `src/agent_mesh/services/repository.py`
- `src/agent_mesh/services/pubsub_setup.py`
- `src/agent_mesh/services/dispatch.py`
- `src/agent_mesh/api/serialization.py`
- `src/agent_mesh/api/app.py`
- `src/agent_mesh/api/mcp_server.py`
- `src/agent_mesh/worker/runner.py`
- `src/agent_mesh/worker/main.py`
- `src/agent_mesh/settings.py`
- `tests/test_approval_security.py`
- `tests/test_repository_sql.py`
- `tests/test_pubsub_dispatch.py`
