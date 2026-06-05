---
phase: 02
slug: real-orchestration-engine
status: verified
threats_open: 0
asvs_level: 2
created: 2026-06-06
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time across all three PLAN.md `<threat_model>` blocks;
> mitigations verified present in implementation by gsd-security-auditor (verify mode,
> not retroactive scan). 14/14 threats closed, ASVS level 2, block_on: high — no blockers.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| package index → build | `pyproject.toml` agents-extra pins pull the LangChain/LangGraph/Deep Agents stack from PyPI | dependency code (supply chain) |
| graph node → roster harness | declared subagents only; no self-spawning | agent topology / capability scope |
| approval endpoint → worker | `/v1/approvals` (HTTP) and MCP verify the signed token — single trusted verification point | approval decision + signed token |
| `Command(resume=...)` → graph | resumed value crosses into the graph; MUST carry only a verified decision, never identity | approval boolean |
| checkpointer store ↔ thread_id | checkpoints key on `thread_id`; tenant scope is NOT free — must be bound via task load | durable run state |
| generated code → host | untrusted prompt-to-code crosses into execution; the container is the only isolation boundary | arbitrary code |
| executor → Docker daemon | `execute_code` invokes `docker run` with hardened cgroup/network/fs/cap flags | container exec request |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-02-01-SC | Tampering (supply chain) | pip install of langgraph / checkpoint×2 / deepagents | mitigate | All first-party langchain-ai packages (RESEARCH legitimacy audit); REQUIRED stack; no postinstall. `pyproject.toml` agents extra; no langsmith in any extra | closed |
| T-02-01-E | Elevation | roster grows beyond declared 4 (auto general-purpose subagent) | mitigate | `roster.py:_disable_general_purpose()` sets `GeneralPurposeSubagentProfile(enabled=False)`; `build_roster()` asserts effective size == 4; logged. `test_roster_is_bounded_at_four` | closed |
| T-02-01-I | Info disclosure | LangSmith auto-tracing leaks prompts | mitigate | LangSmith never imported/enabled; no `LANGCHAIN_TRACING_V2` / `LANGSMITH_API_KEY`. Grep: only UI-label + docstring hits ("optional alternative only") | closed |
| T-02-02-01 | Spoofing / Elevation | forged/self-asserted approver via `Command(resume=...)` | mitigate | `resume_mesh(task, decision)` 2-param, no approver_id; resume carries verified bool only; approver derived ONLY from `verify_approval_token` (fail-closed, SEC-01); graph never reads approver_id. `test_resume_carries_no_identity_channel` | closed |
| T-02-02-02 | Tampering | mutated tool-call payload after approval | mitigate | Write executes only in `runner._resume_after_approval:157` under `approvals.is_approved()` payload-hash re-check (SEC-02a); mutated payload → no execution. `test_mutated_payload_blocks_write_through_resume` | closed |
| T-02-02-03 | Elevation / Info disclosure | cross-tenant / cross-task resume of a checkpoint | mitigate | `thread_id = task.task_id` loaded tenant-scoped (`get_task`, DUR-02); never bare thread_id; token bound to one `approval_record_id` (SEC-02b). `test_checkpointer_resume` uses tenant-scoped thread_id | closed |
| T-02-02-04 | Tampering / Spoofing | interrupt() treated as the approval record (HITL bypass) | mitigate | `write_gate_node` calls `interrupt()` and returns; no Tool Gateway `.execute` in any graph node (grep: sole `.execute(` site is `runner.py:157`); signed-token ledger is decision authority | closed |
| T-02-02-05 | Repudiation | resume-after-restart loses durable state | mitigate | `_select_checkpointer()` → PostgresSaver (prod) / file SqliteSaver (test); `InMemorySaver` forbidden (zero grep hits). Restart-sim proven live: `test_resume_after_restart_sqlite` + `test_resume_after_restart_postgres` (real Postgres) | closed |
| T-02-02-06 | Tampering | resume silently no-ops on stack path (blanket try/except ImportError) defeating ORCH-03 | mitigate | `resume_mesh` gates on `langgraph_available()` (not ImportError swallow); documented second no-op is a value-check on `checkpointer is None`. `test_real_graph_interrupt_pauses_and_resume_mesh_resumes` proves real durable resume. (Register wording "ONLY when absent" superseded — see audit note) | closed |
| T-02-03-01 | DoS | sandboxed code exhausts host memory / outlives timeout | mitigate | cgroup `--memory=Nm --memory-swap=Nm` equal; OOM → exit 137; refuse-to-run-unbounded when Docker absent. **CR-01 fix (d3febd9):** `--name` container + `docker rm -f` on timeout + `--ulimit cpu`; `test_timeout_kills_container` asserts container gone | closed |
| T-02-03-02 | Info disclosure / Exfiltration | sandboxed code reaches the network | mitigate | `--network=none` — no container egress | closed |
| T-02-03-03 | Tampering | sandboxed code writes the host/rootfs | mitigate | `--read-only` rootfs + `--tmpfs /work:rw,size=64m` (only writable surface); snippet bind-mounted `:ro` | closed |
| T-02-03-04 | Elevation | privilege escalation inside the container | mitigate | `--user 65534:65534`, `--cap-drop=ALL`, `--security-opt no-new-privileges`, `--pids-limit=128` | closed |
| T-02-03-05 | DoS / Elevation | fail-open when isolation unavailable | mitigate | `execute_code` raises `SandboxUnavailable` when Docker absent — NEVER an uncapped native subprocess (D-03; closes the old `RLIMIT_AS` fail-open). `test_refuses_unbounded` (always-on) | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|

No accepted risks — all 14 threats mitigated in implementation.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-06 | 14 | 14 | 0 | gsd-security-auditor (sonnet), verify mode |

### Audit notes (non-blocking)

- **IN-02 (pin drift — informational):** core `langgraph-checkpoint` resolves to 4.1.1 transitively; the pinned *backends* `langgraph-checkpoint-sqlite~=3.1` / `-postgres~=3.1` match installed 3.1.0. Reproducibility, not package legitimacy — does not affect T-02-01-SC. (Verified false-alarm in 02-VERIFICATION.md.)
- **T-02-02-06 wording:** implemented design has a two-path no-op (stack-absent stub no-op, plus a value-check no-op when stack present but `DATABASE_URL` unconfigured). Intent (no silent ImportError-swallow) satisfied; the injected-saver test proves real durable resume. Register prose "ONLY when absent" is superseded by the verified two-path design.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-06
