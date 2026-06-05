---
phase: 01-durable-core-approval-security
reviewed: 2026-06-05T08:50:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - .env.example
  - pyproject.toml
  - src/agent_mesh/api/app.py
  - src/agent_mesh/api/mcp_server.py
  - src/agent_mesh/services/approvals.py
  - src/agent_mesh/services/pubsub_setup.py
  - src/agent_mesh/services/repository.py
  - src/agent_mesh/services/self_improvement.py
  - src/agent_mesh/settings.py
  - src/agent_mesh/worker/runner.py
  - tests/conftest.py
  - tests/smoke.py
  - tests/test_approval_gating.py
  - tests/test_approval_security.py
  - tests/test_pubsub_dispatch.py
  - tests/test_repository_sql.py
findings:
  critical: 2
  warning: 4
  info: 1
  total: 7
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-06-05T08:50:00Z
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

Phase 01 implements the durable task lifecycle (RepositorySQL), approval-token security (SEC-01/SEC-02), and the worker pause/resume flow. The HMAC approval token itself is correctly constructed: fail-closed on missing secret, record-id bound, expiry checked, `compare_digest` used, and approver identity derived exclusively from the token rather than the request body. Both `/v1/approvals` and the MCP `submit_approval` tool enforce the gate identically.

However, two Critical findings are present:

1. **The approval token is persisted in plaintext into task metadata and then exposed verbatim through an unauthenticated read endpoint.** Any caller who can read a task ID obtains the bearer token, can POST it to `/v1/approvals`, and self-approve a gated write — recorded in the audit ledger as the legitimate requester. This defeats the entire SEC-01 human-in-the-loop control.

2. **`_resume_after_approval` completes the task unconditionally after its first execution pass.** The design states the worker handles multiple proposed writes; the method iterates all tool calls but then calls `transition_task(COMPLETED)` regardless of how many calls were gated or whether any approved calls were actually executed on this pass. When the real orchestrator emits more than one proposed write, the first resume orphans the remaining calls.

SQL injection posture is clean: all value parameters in RepositorySQL use `%s` placeholders; the only f-string interpolation in queries is over static `_*_COLS` constant strings that contain no runtime-supplied values.

---

## Critical Issues

### CR-01: Approval token leaked through unauthenticated task-read endpoint

**File:** `src/agent_mesh/worker/runner.py:92-99` / `src/agent_mesh/api/app.py:45-50`

**Issue:** After `open_approval` returns `(record, token)`, the worker stores the live HMAC tokens in plain task metadata under the key `"approval_tokens"`:

```python
# runner.py:92-99
metadata["approval_tokens"] = tokens
self._repo.create_task(current.model_copy(update={"metadata": metadata}))
```

`GET /v1/tasks/{task_id}` in `app.py` then returns the complete task record with no authentication, no tenant check, and no redaction:

```python
# app.py:45-50
@app.get("/v1/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, object]:
    task = _service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task.model_dump(mode="json")  # full metadata included
```

Because `RepositorySQL._TASK_COLS` includes the `task_metadata` subquery (`__all__` key), the token is also durable through a DB restart. A caller who knows any task ID (e.g., inferred from a Slack message, leaked in a log, or obtained from another task-creation response) can:

1. `GET /v1/tasks/{task_id}` — reads `metadata.approval_tokens`
2. `POST /v1/approvals` with the retrieved token — self-approved, recorded in the audit ledger as `slack:U1`

The test suite `_pause_on_write` helper itself demonstrates the leak by pulling the token via `repo.get_task(...).metadata["approval_tokens"]`. No test asserts the token is absent from the read response, so the test suite masks the vulnerability.

**Fix:** Tokens must not be written into task metadata at all. The scaffolding note in `runner.py` acknowledges that Slack/MCP postback delivery is deferred; the correct interim behaviour is to log the token (at debug level) or drop it, not to stash it in a readable record. Longer term, deliver the token out-of-band (Slack DM, MCP notification) and do not persist it in any application-readable field.

```python
# runner.py — remove the metadata stash block entirely:
# DELETE lines 92-99 (the issued_tokens accumulation and create_task upsert).
# The record.approval_record_id is already written to the ToolCall row, which
# is sufficient for the worker resume path. The token is not needed there.

# If a delivery channel is later added, deliver via Slack/MCP and discard:
#   deliver_token_to_requester(channel=request.channel, token=token)
#   # do NOT persist token in task metadata
```

Additionally, `GET /v1/tasks/{task_id}` should require authentication (even a bearer header checked against `MODEL_GATEWAY_MASTER_KEY` is better than nothing for the POC) and should never include `metadata["approval_tokens"]` in the response regardless:

```python
# app.py — strip approval_tokens before returning:
@app.get("/v1/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, object]:
    task = _service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    data = task.model_dump(mode="json")
    data.get("metadata", {}).pop("approval_tokens", None)
    return data
```

---

### CR-02: `_resume_after_approval` unconditionally completes the task, orphaning any unapproved writes beyond the first

**File:** `src/agent_mesh/worker/runner.py:106-132`

**Issue:** `_resume_after_approval` iterates all tool calls (`_pending_calls` returns every call for the task, not just those in `AWAITING_APPROVAL`), executes those that pass `is_approved`, marks rejected ones, and then unconditionally calls `transition_task(COMPLETED)` at line 129-131 — regardless of whether any calls were skipped (still pending), how many writes were gated, or whether all approved writes succeeded.

```python
# runner.py:129-132
done = self._repo.transition_task(
    task_id, TaskState.COMPLETED, note="completed after approval"
)
return str(done.state)
```

If the orchestrator ever emits more than one proposed write (which `OrchestrationResult.proposed_writes` is a `list[dict]` and the stub _does_ allow for if triggers overlap), a partial approval leaves remaining `AWAITING_APPROVAL` tool calls stranded in that state permanently: the task is `COMPLETED` and `is_terminal` returns True, preventing any future `process()` call from re-entering.

Additionally, since `_pending_calls` returns **all** tool calls (not just `AWAITING_APPROVAL` ones), if a previously `EXECUTED` call happens to still match `is_approved` on re-entry it would be re-executed. The terminal-state check at the top of `process()` prevents re-entry after `COMPLETED`, but between the first `APPROVED`→`RUNNING` re-dispatch and `COMPLETED`, a race window exists.

The stub currently emits at most one write, so this is latent rather than immediately triggering — but the data model explicitly supports multiple writes.

**Fix:** Before transitioning to `COMPLETED`, verify that no tool call remains in `AWAITING_APPROVAL`:

```python
def _resume_after_approval(self, task_id: str) -> str:
    task = self._repo.get_task(task_id)
    assert task is not None
    for call in self._pending_calls(task_id, task.tenant_id):
        if call.status not in (
            ToolCallStatus.AWAITING_APPROVAL.value, ToolCallStatus.AWAITING_APPROVAL
        ):
            continue  # skip already-executed or rejected calls
        if call.approval_record_id is None:
            continue
        record = self._repo.get_approval(call.approval_record_id)
        if record is None:
            continue
        if approvals.is_approved(record, call.parameters):
            result = self._execute(call)
            executed = call.model_copy(
                update={"status": ToolCallStatus.EXECUTED.value, "result": result}
            )
            self._repo.upsert_tool_call(executed)
        elif record.decision in (
            ApprovalDecision.REJECTED.value, ApprovalDecision.REJECTED
        ):
            rejected = call.model_copy(update={"status": ToolCallStatus.REJECTED.value})
            self._repo.upsert_tool_call(rejected)

    # Only complete if nothing is still awaiting approval.
    still_pending = [
        c for c in self._pending_calls(task_id, task.tenant_id)
        if c.status in (ToolCallStatus.AWAITING_APPROVAL.value, ToolCallStatus.AWAITING_APPROVAL)
    ]
    if still_pending:
        return str(TaskState.AWAITING_APPROVAL.value)

    done = self._repo.transition_task(
        task_id, TaskState.COMPLETED, note="completed after approval"
    )
    return str(done.state)
```

Also rename `_pending_calls` to `_all_calls` to eliminate the misleading implication that it returns only pending calls.

---

## Warnings

### WR-01: Single-entity `get_*` reads in RepositorySQL are not tenant-scoped

**File:** `src/agent_mesh/services/repository.py:538-543, 634-640, 678-685, 738-745, 772-779, 823-830`

**Issue:** DUR-02 requires tenant isolation on every read path. All `list_*` queries (events, tool_calls, approvals, evaluations) include `AND tenant_id = %s`. But the single-entity `get_*` queries accept only the primary key:

```python
# repository.py:538-543
def get_task(self, task_id: str) -> TaskRecord | None:
    row = conn.execute(
        f"SELECT {_TASK_COLS} FROM tasks WHERE task_id = %s", (task_id,)
    ).fetchone()

# Same pattern for get_tool_call, get_approval, get_proposal, get_evaluation, get_promotion
```

An adversary who obtains a primary-key UUID from one tenant (e.g., via an error message, log entry, or other side channel) can call `GET /v1/tasks/{task_id}` and retrieve a record belonging to a different tenant, because `app.py` calls `_service.get_task(task_id)` → `repo.get_task(task_id)` with no tenant context at all.

`test_cross_tenant_reads_return_empty` only covers the `list_*` set, leaving this gap untested.

Primary-key UUIDs (`uuid4().hex`) are hard to guess, so real-world exploitability is low. But the DUR-02 guarantee states "every read path" and this is a documented design requirement.

**Fix:** Add `tenant_id` parameters to all `get_*` signatures and add `AND tenant_id = %s` to every single-entity query. API endpoints that have a caller-supplied tenant (from auth context or settings) should pass it through.

---

### WR-02: Approval token is reusable within its full TTL (no single-use enforcement)

**File:** `src/agent_mesh/services/approvals.py:104-146`

**Issue:** `verify_approval_token` has no nonce or consumed-state check. A valid token can be presented to `/v1/approvals` or the MCP `submit_approval` tool multiple times within its 1-hour TTL. The ledger's `ON CONFLICT DO UPDATE` means repeated approval submissions for the same record just overwrite the decision — which is benign for the same decision but allows a captured token to be replayed an arbitrary number of times.

More concretely, if a decision of `REJECTED` is recorded by a legitimate action, a replay of the original `APPROVED` token (within TTL) would overwrite it with `APPROVED`, and the task would be re-dispatched. The `submit_approval_decision` path calls `transition_task(APPROVED)` again, which would trigger an `IllegalTransition` from `REJECTED` and raise (protecting against the state transition), but the approval record itself would be overwritten first.

**Fix:** After a decision is recorded successfully, mark the approval record as consumed and reject any further token presentations for that record:

```python
# In verify_approval_token, after HMAC passes, check if already decided:
if record.decision != ApprovalDecision.PENDING.value and record.decision != ApprovalDecision.PENDING:
    return None  # token already consumed; reject replay
```

---

### WR-03: Invalid `decision` value raises unhandled `ValueError` — 500 instead of 400

**File:** `src/agent_mesh/api/app.py:100-103` / `src/agent_mesh/api/mcp_server.py:49`

**Issue:** In `app.py`, the `KeyError` catch on line 102-103 catches only missing fields, not invalid values:

```python
# app.py:100-103
try:
    approval_record_id = payload["approval_record_id"]
    decision = ApprovalDecision(payload["decision"])   # raises ValueError on bad value
except KeyError as exc:
    raise HTTPException(status_code=400, detail=f"missing field: {exc}") from exc
```

Submitting `"decision": "maybe"` raises `ValueError` outside the `except KeyError` block, propagating as an unhandled exception and returning HTTP 500 rather than 400. Similarly in `mcp_server.py:49`, `ApprovalDecision(decision)` raises `ValueError` on an invalid string and is not caught, producing an unstructured Python exception bubbling out of the MCP tool.

**Fix:**

```python
# app.py
try:
    approval_record_id = payload["approval_record_id"]
    try:
        decision = ApprovalDecision(payload["decision"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid decision value: {exc}") from exc
except KeyError as exc:
    raise HTTPException(status_code=400, detail=f"missing field: {exc}") from exc
```

For `mcp_server.py`, wrap `ApprovalDecision(decision)` in a try/except and return an error dict:

```python
try:
    decided = service.submit_approval_decision(
        approval_record_id=approval_record_id,
        decision=ApprovalDecision(decision),
        ...
    )
except ValueError as exc:
    return {"error": f"invalid decision: {exc}"}
```

---

### WR-04: `transition_task` in RepositorySQL is non-atomic — state UPDATE and audit event INSERT are in separate transactions

**File:** `src/agent_mesh/services/repository.py:559-571`

**Issue:** The comment on line 558 says "Single transaction: UPDATE state AND append the audit event atomically (Pitfall 7)", but the implementation opens the pool connection, executes both statements, and then immediately closes the `with` block — this is correct for a single `with self._pool.connection()` block. However, `get_task` at line 569 opens a **second** connection:

```python
# repository.py:559-571
with self._pool.connection() as conn:
    conn.execute("UPDATE tasks SET state=%s ...", ...)
    conn.execute("INSERT INTO task_events ...", ...)
# Connection (transaction) committed here.
result = self.get_task(task_id)   # NEW connection — outside the transaction
```

The two DML statements are correctly in one transaction; the atomicity claim is valid. However, between the commit and the `get_task` read, another writer can modify the row, causing `transition_task` to return a stale or differently-modified task record that does not reflect the state just written. This is a classic TOCTOU on the re-read. For the single-writer POC this is benign, but the comment says "atomic" and the returned object is not the same row that was committed.

**Fix:** Either return the computed object directly (without the re-read), or move the `SELECT` inside the same transaction using `RETURNING *`. The simplest approach for the POC:

```python
# Remove the re-read; return a local copy of the updated task.
# (Requires fetching current before update, which is already done.)
updated_task = current.model_copy(
    update={"state": target_value, "updated_at": datetime.now(UTC)}
)
return updated_task
```

---

## Info

### IN-01: `_pending_calls` misleadingly named — returns all tool calls for the task

**File:** `src/agent_mesh/worker/runner.py:134-137`

**Issue:** The method name implies it returns only pending/awaiting calls, but it returns every `ToolCall` for the `(task_id, tenant_id)` pair regardless of status. The caller in `_resume_after_approval` then filters inside the loop. This naming defect contributed directly to CR-02 (the all-calls iteration in the resume path).

**Fix:** Rename to `_all_calls` or `_task_calls`, and document clearly that callers are responsible for filtering by status:

```python
def _all_calls(self, task_id: str, tenant_id: str) -> list[ToolCall]:
    """Return all ToolCall records for this task (any status)."""
    return self._repo.list_tool_calls(task_id, tenant_id)
```

---

_Reviewed: 2026-06-05T08:50:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
