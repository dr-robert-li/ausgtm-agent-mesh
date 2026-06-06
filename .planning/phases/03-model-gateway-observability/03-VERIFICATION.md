---
phase: 03-model-gateway-observability
verified: 2026-06-06T06:21:00Z
status: gaps_found
score: 4/5 must-haves verified (1 partial counts as gap)
overrides_applied: 0
gaps:
  - truth: "When the primary model fails, the cascade falls back and the run continues; a budget breach halts the run"
    status: partial
    reason: >
      Cascade fallback proven (stub-lane + live-lane structural wiring). Budget spend-stop proven
      (BudgetExceeded raised pre-call, test_cascade_live exercises round-trip). Two sub-gaps remain:
      (1) BudgetExceeded propagates uncaught through _delegate → LangGraph node — no explicit
      catch to write a GatewayEvent or set a terminal task state; the run halts as an unhandled
      graph exception, not a governed halt. (2) record_gateway_event is declared in all three
      Repository implementations but has zero call sites in production src — the halt-observability
      contract (gateway_event row for model_route="budget_halt") is not wired.
    artifacts:
      - path: "src/agent_mesh/worker/graph.py"
        issue: "_delegate line 154 calls budget.check() which raises BudgetExceeded; no except block
          catches it to record a gateway_event or set task state to FAILED. record_gateway_event
          has 0 call sites in this file (grep confirmed)."
      - path: "src/agent_mesh/worker/budget.py"
        issue: "BudgetExceeded raised at line 101; no call to record_gateway_event on halt path."
    missing:
      - "Add except BudgetExceeded block in _delegate (graph.py) that calls repo.record_gateway_event(GatewayEvent(model_route='budget_halt', dlp_action='block', provider_status=None, tenant_id=..., task_id=...)) before re-raising."
      - "Ensure BudgetExceeded propagates to orchestrator as a recognizable halt (e.g. set task state to FAILED with halt reason) rather than an untyped graph exception."
  - truth: "Every model, tool, and approval event for a task appears correlated in Langfuse under shared request metadata"
    status: partial
    reason: >
      Model-run and approval events are instrumented (OTel spans with trace_metadata() attributes;
      Langfuse LangChain callback wired in _graph_config). Tool-execution spans are NOT wired:
      src/agent_mesh/tools/ has no OTel instrumentation. Real tool adapters are Phase 4 (TOOL-01),
      so this is a phased deferral — but as written, SC-3 says "tool events" are correlated, which
      is not yet true. Recorded as a gap; addressed in Phase 4.
    artifacts:
      - path: "src/agent_mesh/tools/"
        issue: "No trace_metadata(), start_as_current_span, or OTel span instrumentation found in
          any file under this directory (grep returned 0 matches)."
    missing:
      - "Wire tool-execution OTel spans (start_as_current_span with trace_metadata() attrs) in the
        Tool Gateway adapter call path — deferred to Phase 4 / TOOL-01."
deferred:
  - truth: "Tool-execution events correlated in Langfuse (the 'tool events' sub-clause of SC-3 / OBS-01)"
    addressed_in: "Phase 4"
    evidence: "Phase 4 goal: 'real SaaS tool adapter execute through the gated Tool Gateway'; TOOL-01
      success criterion: 'A real SaaS tool adapter performs a real call locally through the Tool
      Gateway with credentials resolved at execution time.' OTel instrumentation of that path is the
      natural attachment point."
---

# Phase 3: Model Gateway & Observability Verification Report

**Phase Goal:** Stand up the live LiteLLM-compatible model control plane with budget enforcement and cascades, route upstream through the Cloudflare AI Gateway governance plane, and wire Langfuse so every model/tool/approval event is traced and correlated.
**Verified:** 2026-06-06T06:21:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | Model calls route through live LiteLLM gateway and halt cleanly when USD $50 budget exhausted | PARTIAL | Routing: `RouterChatLiteLLM._router.completion()` at `model_gateway.py:67-81`. Halt: `budget.check()` raises `BudgetExceeded` at `budget.py:101`. NOT CLEAN: exception propagates uncaught — no gateway_event row, no governed terminal state. |
| SC-2 | Primary model failure triggers cascade fallback; budget breach halts the run | PARTIAL | Fallback proven: `test_cascade.py` (stub-lane `mock_testing_fallbacks=True`) + `test_cascade_live.py` (live-lane Vertex→Anthropic structural path). Budget halt: raises `BudgetExceeded` pre-call (verified). Clean halt governance not wired — see SC-1 gap. |
| SC-3 | Every model, tool, and approval event correlated in Langfuse under shared request metadata | PARTIAL | Model: `_task_root_span` + `_graph_config` callbacks at `orchestrator.py:195-215,250-260`. Approval: `_approval_span` at `approvals.py:160-192`. Tool: 0 OTel call sites under `src/agent_mesh/tools/` (grep confirmed). Tool instrumentation deferred to Phase 4. |
| SC-4 | Upstream model calls traverse Cloudflare AI Gateway when enabled; agents never call providers directly | VERIFIED | D-06 structural guard: `api_base` absent from all `RouterChatLiteLLM` constructor calls (grep=0 in non-comment lines). AST guard in `test_d06_chokepoint.py` walks every `.py` under `src/agent_mesh` and fails on `ChatAnthropic`/`ChatVertexAI` import or `litellm.completion(` call. CF URL resolved per-route in yaml `litellm_params.api_base` when `CF_ENABLED`. |

**Score:** 2 fully verified / 4 must-have truths (SC-1, SC-2 partial; SC-3 partially deferred to Phase 4; SC-4 verified)

---

## Per-REQ-ID Verdicts

### GW-01 — LiteLLM-compatible gateway with cascades and per-user/per-task budget enforcement

**Acceptance criteria:** A live LiteLLM-compatible gateway routes to Anthropic-direct and Vertex AI with cascades and enforces a USD $50/month per-user/per-task budget.

**VERDICT: PARTIAL**

Evidence for routing:
- `model_gateway.py:55-90`: `build_router(config_path)` constructs `litellm.Router` from yaml `model_list` with `fallbacks` and `num_retries`.
- `model_gateway.py:60-80`: `RouterChatLiteLLM(ChatLiteLLM)` subclass: `_router: Any = PrivateAttr()`; `completion_with_retry → self._router.completion()`; `acompletion_with_retry → await self._router.acompletion()` — defeats langchain_litellm validator clobber at `litellm.py:558`.
- `model_gateway.py:~196-197`: comment confirms `api_base` deliberately absent from constructor; lives in yaml per-route.
- `test_model_gateway_router.py`: stub-Router asserts routing override path.

Evidence for budget:
- `budget.py:85-101`: `BudgetTracker.check(budget_owner, incremental_usd, *, tenant_id, task_id=None)` reads `month_to_date` from repo; raises `BudgetExceeded` on breach.
- `budget.py`: grep `self._spent[` in non-comment lines → 0 (no in-memory dict; fully repo-backed).
- `test_budget_ledger.py`: durable ledger, tenant-scoped, `BudgetExceeded` round-trip.

Known limitation (POC-documented):
- `graph.py:143`: `budget_owner = settings.tenant_id` — per-user enforcement collapses to per-tenant until ingress threads `requester_id` through graph state (TODO comment inline).
- `budget.py (_task_to_date SQL path)`: returns `0.0` conservatively on SQL backend; per-task cap fully operative on InMemory path only.

These limitations are documented in source as POC-phase deferrals. The gateway routes correctly and `BudgetExceeded` fires before spend. Verdict is PARTIAL because per-user granularity is structurally absent on the live path.

---

### GW-02 — Gateway routes all upstream model calls through Cloudflare AI Gateway when enabled; agents never call providers directly

**Acceptance criteria:** The gateway routes all upstream model calls through the Cloudflare AI Gateway when enabled; agents never call providers directly.

**VERDICT: VERIFIED**

Evidence:
- `model_gateway.py:~196-197`: `api_base` never passed to `RouterChatLiteLLM` constructor — confirmed by grep on non-comment lines (0 matches for `api_base=` in constructor call context).
- CF URL resolved per-route: yaml `litellm_params.api_base` set to CF wrapper URL when `CF_ENABLED`.
- `test_d06_chokepoint.py`: AST guard walks all `.py` under `src/agent_mesh`; fails build on `ChatAnthropic`, `ChatVertexAI`, or `litellm.completion(` — confirmed 0 violations.
- D-06 design decision: `api_base` lives in `model_list[*].litellm_params.api_base` in router yaml, not on any chat model constructor; CF wrapper URL resolves per-route only when CF enabled.

Structural guarantee: construction path for all model calls is `get_chat_model(tier)` → `RouterChatLiteLLM` → `_router.completion()` → yaml-configured route → (CF upstream when enabled) → provider. No agent or worker has a direct provider client constructor.

Note: CF integration is structural/integration-ready for POC. Live CF traffic routing requires `CF_ENABLED=true` and a configured `CLOUDFLARE_AI_GATEWAY_ID` at runtime (no live GCP provisioning in this milestone).

---

### GW-03 — Failure test proves model fallback and budget-limit halt behave correctly

**Acceptance criteria:** A failure test proves model fallback and budget-limit halt behave correctly.

**VERDICT: PARTIAL**

Evidence — fallback (PASS):
- `tests/test_cascade.py`: stub-lane, `mock_testing_fallbacks=True` + `mock_response`; proves routing cascade fires on primary failure. No creds required.
- `tests/test_cascade_live.py`: live-lane, nonexistent Vertex model → real Anthropic fallback; cents-cap halt against real provider. Skipped without creds; structural path proven.

Evidence — budget halt (PARTIAL):
- `tests/test_cascade_live.py:163-180`: live-lane test calls `repo.record_gateway_event(GatewayEvent(model_route="budget_halt", dlp_action="block", ...))` manually in the test body to assert the ledger contract.
- `tests/test_budget_ledger.py`: `BudgetExceeded` raised and durable-ledger round-trip verified.
- MISSING: `src/agent_mesh/worker/graph.py` has 0 call sites for `record_gateway_event` (grep confirmed). The production `_delegate` BudgetExceeded halt path does NOT emit a gateway_event row.
- MISSING: `BudgetExceeded` propagates uncaught from `_delegate` → LangGraph node → graph executor. No `except BudgetExceeded` block sets a terminal task state or emits an event before re-raising.

Gap contract (what a future plan must add to `graph.py`):
```python
from agent_mesh.contracts.models import GatewayEvent
from agent_mesh.services.repository import get_repository

try:
    budget.check(budget_owner, estimate, tenant_id=settings.tenant_id)
    # ... model call ...
except BudgetExceeded:
    repo.record_gateway_event(
        GatewayEvent(
            model_route="budget_halt",
            dlp_action="block",
            provider_status=None,
            tenant_id=settings.tenant_id,
            task_id=<task_id from state>,
        )
    )
    raise  # re-raise for orchestrator to set FAILED state
```
The orchestrator must catch `BudgetExceeded` (or a typed subclass) to write a terminal task state rather than letting it surface as an untyped graph exception.

---

### OBS-01 — Langfuse telemetry wired so spans, token/cost, and task/tool/approval events correlate via shared request metadata

**Acceptance criteria:** Langfuse telemetry is wired so spans, token/cost, and task/tool/approval events correlate via shared request metadata.

**VERDICT: PARTIAL** (tool-event sub-clause deferred to Phase 4; model + approval sub-clauses VERIFIED)

Evidence — OTel transport:
- `observability.py:106-177`: `init_tracing()` builds `TracerProvider` WITHOUT setting global; `SimpleSpanProcessor(test_exporter)` for CI; `BatchSpanProcessor(OTLPSpanExporter(endpoint=...))` for live Langfuse OTLP.
- `observability.py:185-218`: test-injectable `set_tracer_provider_override()` / `get_tracer()` — isolated per-test exporters, no global clobber.
- `tests/test_observability_otel.py`: `InMemorySpanExporter` asserts span attributes.
- `tests/test_trace_propagation.py`: real store→restore end-to-end (traceparent persisted on TaskRecord, extracted in worker).

Evidence — shared metadata:
- `observability.py:79-103`: `trace_metadata()` builds dict with `tenant_id`, `client_slug`, `task_id`, `session_id`, `requester_id`, `entrypoint`, `agent_role`, `model_route_profile`, `approval_state`.
- `observability.py:221-233`: `set_span_metadata(span, metadata)` writes all non-None keys as span attributes.

Evidence — model spans:
- `orchestrator.py:195-215`: `_task_root_span(task, "mesh.run")` contextmanager; restores `task.metadata["traceparent"]` via `obs.extract_otel_context`; sets span metadata; yields `obs.span_trace_id(span)`.
- `orchestrator.py:213,338,359,375`: `result.trace_id = trace_id` set on ALL return paths (run_mesh + 3 resume_mesh branches).

Evidence — Langfuse LangChain callback:
- `observability.py:272-292`: `get_langchain_callback()` lazy-imports `from langfuse.langchain import CallbackHandler` (v4 path; `from langfuse.callback import` is DEAD under 4.x — grep confirmed 0 non-comment matches).
- `orchestrator.py:250-260`: `_graph_config(task)` sets `config["callbacks"] = [handler]` when callback available.

Evidence — approval spans:
- `approvals.py:160-192`: `_approval_span()` contextmanager wraps `open_approval` and `record_decision`; calls `obs.trace_metadata()` + `obs.set_span_metadata()`.

Evidence — W3C traceparent cross-process:
- `app.py:49-51`: `traceparent = http_request.headers.get("traceparent")`; stored in `request.metadata["traceparent"]` before `create_task()`.
- `orchestrator.py`: `obs.extract_otel_context(traceparent)` restores parent context in worker.

Gap — tool spans:
- `src/agent_mesh/tools/` has no OTel instrumentation (grep for `trace_metadata\|start_span\|start_as_current_span` returned 0 matches).
- Real tool adapters are Phase 4 / TOOL-01. Recorded as deferred gap.

---

### OBS-02 — Langfuse prompt/version management and datasets/evals configured

**Acceptance criteria:** Langfuse prompt/version management and datasets/evals are configured.

**VERDICT: VERIFIED**

Evidence:
- `observability.py:295-318`: `get_prompt_with_fallback(name, local_default)` fetches named versioned prompt from Langfuse when reachable; returns `local_default` offline (stub-fallback invariant).
- `tests/test_langfuse_prompts.py`: offline fallback path verified without creds.
- `tests/test_langfuse_seed_live.py`: live-lane seeds versioned prompt, dataset, and eval scores into Langfuse. Skipped without creds; structural path proven.

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/agent_mesh/worker/model_gateway.py` | LiteLLM Router + RouterChatLiteLLM | VERIFIED | `build_router()`, `RouterChatLiteLLM`, `get_chat_model()`, `TIER_TO_DEPLOYMENT` all present and substantive |
| `src/agent_mesh/worker/budget.py` | Durable BudgetTracker, BudgetExceeded | VERIFIED | Repo-backed; no `_spent` dict (grep=0); `check()` + `record()` wired |
| `src/agent_mesh/observability.py` | OTel + Langfuse v4 seam | VERIFIED | `init_tracing()`, `get_langchain_callback()` (v4 path), `get_prompt_with_fallback()`, `trace_metadata()`, `extract_otel_context()`, `span_trace_id()` all present |
| `src/agent_mesh/api/app.py` | traceparent capture at ingress | VERIFIED | Lines 49-51: reads `traceparent` header, stores in `request.metadata` |
| `src/agent_mesh/worker/orchestrator.py` | trace_id on all return paths | VERIFIED | `_task_root_span()` + `result.trace_id = trace_id` at lines 213, 338, 359, 375 |
| `src/agent_mesh/services/approvals.py` | approval OTel spans | VERIFIED | `_approval_span()` contextmanager wraps `open_approval` + `record_decision` |
| `tests/test_model_gateway_router.py` | GW-01 router stub proof | VERIFIED | Exists, exercises RouterChatLiteLLM routing override |
| `tests/test_budget_ledger.py` | GW-01 durable ledger proof | VERIFIED | Exists, exercises BudgetExceeded + tenant-scoped ledger |
| `tests/test_d06_chokepoint.py` | GW-02 AST structural guard | VERIFIED | Exists, AST-walks src, fails on ChatAnthropic/ChatVertexAI/litellm.completion |
| `tests/test_cascade.py` | GW-03 stub-lane cascade | VERIFIED | Exists, mock_testing_fallbacks cascade proof |
| `tests/test_cascade_live.py` | GW-03 live-lane cascade + halt | VERIFIED (structural) | Exists; live-lane skips without creds; gateway_event call is MANUAL (test only, not from _delegate) |
| `tests/test_observability_otel.py` | OBS-01 span emission | VERIFIED | Exists, InMemorySpanExporter assertions |
| `tests/test_trace_propagation.py` | OBS-01 cross-process traceparent | VERIFIED | Exists, real store→restore end-to-end |
| `tests/test_langfuse_prompts.py` | OBS-02 offline fallback | VERIFIED | Exists, fallback path without creds |
| `tests/test_langfuse_seed_live.py` | OBS-02 live seed | VERIFIED (structural) | Exists; live-lane skips without creds |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `graph.py:_delegate` | `RouterChatLiteLLM` | `get_chat_model(tier)` | WIRED | Sole construction path; D-06 guardrail holds |
| `RouterChatLiteLLM` | `litellm.Router` | `_router.completion()` | WIRED | PrivateAttr set in `get_chat_model()` after construction |
| `litellm.Router` | CF/provider | `api_base` in yaml per-route | WIRED (structural) | Live only when `CF_ENABLED`; yaml configures route |
| `app.py:create_task` | `TaskRecord.metadata["traceparent"]` | lines 49-51 | WIRED | Confirmed in source |
| `orchestrator.py:_task_root_span` | OTel span + trace_id | `obs.extract_otel_context` | WIRED | All run_mesh + resume_mesh branches set `result.trace_id` |
| `orchestrator.py:_graph_config` | Langfuse callback | `config["callbacks"]` | WIRED | `get_langchain_callback()` → `CallbackHandler()` |
| `approvals.py:open_approval` | OTel span | `_approval_span()` contextmanager | WIRED | Wraps both open and decision paths |
| `graph.py:_delegate` | `repo.record_gateway_event` | BudgetExceeded catch | NOT WIRED | 0 call sites in graph.py (grep confirmed) — BLOCKER for SC-1/GW-03 |
| `tools/` | OTel span | `trace_metadata()` + `start_as_current_span` | NOT WIRED | 0 instrumentation in tools dir; deferred Phase 4 |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `observability.py:get_langchain_callback` | `CallbackHandler` | `langfuse.langchain` (v4) | Yes (live); None (offline) | VERIFIED — degrades gracefully |
| `budget.py:BudgetTracker.check` | `month_to_date` | `repo.budget_month_to_date()` | Yes (InMemory); 0.0 (SQL POC) | PARTIAL — SQL path returns 0.0 (documented POC limitation) |
| `orchestrator.py:run_mesh` | `result.trace_id` | `obs.span_trace_id(span)` | Yes — from real OTel span context | VERIFIED |
| `app.py:create_task` | `request.metadata["traceparent"]` | HTTP `traceparent` header | Yes — from inbound W3C header | VERIFIED |

---

## Behavioral Spot-Checks

Default-lane (no creds) suite run performed prior to this report:

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 3 default-lane tests (40 tests) | `PYTHONPATH=src .venv/bin/pytest tests/test_model_gateway_router.py tests/test_budget_ledger.py tests/test_d06_chokepoint.py tests/test_cascade.py tests/test_observability_otel.py tests/test_trace_propagation.py tests/test_langfuse_prompts.py -x -q` | 40 passed | PASS |
| Full default suite | `PYTHONPATH=src .venv/bin/pytest -x -q --ignore=tests/test_cascade_live.py --ignore=tests/test_langfuse_seed_live.py` | 129 passed, 1 pre-existing Docker flake (SBX-01 / Phase 2) | PASS (Phase 3 scope) |
| Live-lane (creds) | `tests/test_cascade_live.py`, `tests/test_langfuse_seed_live.py` | Skipped — no model/Langfuse credentials in local env | SKIP (needs live creds) |

Pre-existing failure note: `test_sandbox::test_timeout_kills_container` exits code 125 — Docker container name conflict from stale container (left over from prior Phase 2 run). This test is Phase 2 / SBX-01 scope; not introduced by Phase 3. Phase 3 tests are all green.

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| GW-01 | 03-01 | LiteLLM-compatible gateway, budgets, cascades | PARTIAL | Routing + BudgetExceeded: VERIFIED. Per-user granularity collapses to per-tenant (graph.py:143 TODO). SQL per-task returns 0.0. |
| GW-02 | 03-02 | All upstream model calls through CF AI Gateway; agents never direct | VERIFIED | AST guard + grep=0. CF routing structural, integration-ready. |
| GW-03 | 03-02 | Failure test: fallback + budget halt | PARTIAL | Fallback: VERIFIED (stub+live-lane). Halt: spend-stop proven; gateway_event NOT emitted by _delegate; uncaught exception. |
| OBS-01 | 03-03 | Langfuse telemetry: spans + token/cost + model/tool/approval events, shared metadata | PARTIAL | Model + approval spans: VERIFIED. Tool spans: not wired (deferred Phase 4). traceparent cross-process: VERIFIED. |
| OBS-02 | 03-03 | Langfuse prompt/version management + datasets/evals | VERIFIED | `get_prompt_with_fallback()` + offline fallback test + live seed test (structural). |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/agent_mesh/worker/graph.py` | 140-143 | `# TODO(03-02/ingress): budget_owner is the requester id...` + `budget_owner = settings.tenant_id` | Warning | Per-user budget enforcement collapses to per-tenant on live path. Documented POC deferral; no formal issue reference. |
| `src/agent_mesh/worker/graph.py` | 303 | Stale comment: `# trace_id stays unset — Langfuse correlation is Phase 3` | Info | trace_id IS set by outer run_mesh context manager; comment is misleading but not a bug. No correctness impact. |
| `src/agent_mesh/worker/budget.py` | `_task_to_date SQL` | `return 0.0` on SQL path | Warning | Per-task cap not enforced on SQL backend; InMemory-only limitation. Documented in source. |

No `TBD`, `FIXME`, or `XXX` markers found in Phase 3 modified files (only `TODO` with inline explanation).

---

## Human Verification Required

### 1. Live Cascade Fallback — Real Vertex → Anthropic

**Test:** Set real Vertex AI and Anthropic credentials. Run `pytest tests/test_cascade_live.py -v -m live` (or remove the skip condition). Verify a real Vertex model failure triggers automatic fallback to the Anthropic route and returns a valid response.
**Expected:** Test passes; litellm Router logs show primary failure and fallback activation; no direct provider call bypasses the gateway.
**Why human:** Requires live model credentials not present in CI.

### 2. Live Budget Halt Against Real Provider

**Test:** Configure a sub-cent budget cap. Run `pytest tests/test_cascade_live.py::test_budget_halt_live -v`. Verify `BudgetExceeded` is raised before any tokens are consumed against the real provider.
**Expected:** `BudgetExceeded` raised; ledger shows pre-call check; no provider charge.
**Why human:** Requires live model credentials; real token spend risk.

### 3. Langfuse Live Trace Correlation

**Test:** With `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` set, run a mesh task end-to-end. Open Langfuse UI and confirm: (a) run span has `tenant_id`, `task_id`, `requester_id` attributes; (b) approval events appear as child spans under the same `task_id`; (c) LangChain callback spans carry token/cost metadata.
**Expected:** All three event types visible and correlated by `task_id` in Langfuse session view.
**Why human:** Requires live Langfuse instance; UI correlation cannot be grep-verified.

### 4. Cloudflare AI Gateway Traffic Routing

**Test:** Set `CF_ENABLED=true` + `CLOUDFLARE_AI_GATEWAY_ID`. Run a model call. Inspect CF AI Gateway logs to confirm the request traversed CF before reaching the provider.
**Expected:** CF logs show the model request with `tenant_id`/`task_id` metadata attached.
**Why human:** Requires live CF account and gateway configuration; not testable without provisioning.

---

## Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Tool-execution OTel spans not wired in `src/agent_mesh/tools/` | Phase 4 | Phase 4 goal: real SaaS tool adapter through Tool Gateway; TOOL-01 SC: "A real SaaS tool adapter performs a real call locally through the Tool Gateway." OTel instrumentation is the natural attachment point for that path. |

---

## Gaps Summary

Two gaps block full goal achievement:

**Gap 1 — GW-03 / SC-1 / SC-2: Budget halt path not governed (halt-observability + clean-halt wiring)**

The production `_delegate` in `graph.py` raises `BudgetExceeded` but has no handler. No `gateway_event` row is written on the halt path — `record_gateway_event` has zero call sites in all production `src/` outside repository declarations. The halt surfaces as an unhandled LangGraph node exception rather than a governed terminal state with an auditable event. The test in `test_cascade_live.py` calls `record_gateway_event` manually to assert the ledger contract, but this does not wire the production path.

Fix: add an `except BudgetExceeded` block in `_delegate` that calls `repo.record_gateway_event(GatewayEvent(model_route="budget_halt", dlp_action="block", ...))` before re-raising, and add an orchestrator-level catch to transition the task to a FAILED terminal state.

**Gap 2 — OBS-01 / SC-3: Tool-event spans not wired (deferred to Phase 4)**

`src/agent_mesh/tools/` has no OTel instrumentation. The "tool events" sub-clause of SC-3 is unmet. Real tool adapters arrive in Phase 4; this gap is phased, not an oversight. Recorded here for completeness; no remediation needed before Phase 4.

---

_Verified: 2026-06-06T06:21:00Z_
_Verifier: Claude (gsd-verifier)_
