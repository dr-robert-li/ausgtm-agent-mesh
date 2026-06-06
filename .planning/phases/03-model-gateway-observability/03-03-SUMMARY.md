---
phase: 03-model-gateway-observability
plan: 03
subsystem: observability
tags: [langfuse, opentelemetry, otel, tracing, obs-01, obs-02, traceparent, prompt-versioning]
requires:
  - "observability.trace_metadata() + langfuse_available() (Phase 1/2)"
  - "settings.otel_exporter_otlp_endpoint + langfuse_* fields (03-01)"
  - "pyproject langfuse>=4,<5 + opentelemetry HTTP deps (03-01)"
  - "conftest span_exporter + live_creds fixtures (03-01)"
  - "api/app.py POST /v1/tasks + TaskService.create_task metadata copy (Phase 1/2)"
  - "worker/orchestrator.py _run_langgraph/resume_mesh + OrchestrationResult (Phase 2)"
  - "services/approvals.py signed-token gate SEC-01/02 (Phase 1)"
provides:
  - "init_tracing(settings, test_exporter=) OTel TracerProvider (in-memory CI / OTLP-HTTP Langfuse) + parallel-SIEM seam"
  - "get_tracer()/set_tracer_provider_override() test-injection seam (no global OTel provider mutation)"
  - "extract_otel_context()/span_trace_id()/set_span_metadata() span helpers"
  - "per-task root span (mesh.run/mesh.resume) restoring inbound traceparent; OrchestrationResult.trace_id SET on every path"
  - "real-ingress traceparent store at POST /v1/tasks; worker restore across Pub/Sub"
  - "read-only OTel approval spans (open_approval/record_decision) carrying shared metadata"
  - "langfuse v4 CallbackHandler (langfuse.langchain) attached to the graph run (None-safe)"
  - "get_prompt_with_fallback() OBS-02 offline fallback + live-lane prompt/dataset/eval seed"
affects:
  - "Phase 4 (self-improvement evals build on the OBS-02 Langfuse-native dataset/eval seam)"
  - "Phase 5 (deploy-readiness: OTLP endpoint + langfuse creds become live-lane runtime config)"
tech-stack:
  added: []
  patterns:
    - "no-global-provider OTel: init_tracing returns a provider; get_tracer uses an injectable override so per-test InMemorySpanExporters stay isolated (set_tracer_provider is install-once)"
    - "trace_id derived from the SAME span context the run roots under (format(trace_id,'032x')), not a free-standing minted id"
    - "W3C traceparent restore via TraceContextTextMapPropagator().extract as the OTel parent context across the Pub/Sub boundary"
    - "read-only telemetry span: @contextmanager wrapping, never branches on span data (RF-1)"
key-files:
  created:
    - "tests/test_observability_otel.py"
    - "tests/test_trace_propagation.py"
    - "tests/test_langfuse_prompts.py"
    - "tests/test_langfuse_seed_live.py"
  modified:
    - "src/agent_mesh/observability.py"
    - "src/agent_mesh/api/app.py"
    - "src/agent_mesh/worker/orchestrator.py"
    - "src/agent_mesh/services/approvals.py"
    - "tests/test_orchestration_graph.py"
decisions:
  - "init_tracing returns a TracerProvider WITHOUT calling set_tracer_provider; get_tracer resolves a test-injected override first, else a process-cached provider. OTel's global provider is install-once-per-process, so a global would leak spans across the 3 test files run in one pytest process (the second exporter would see zero spans). The injection seam keeps each test's InMemorySpanExporter isolated."
  - "OrchestrationResult.trace_id is derived from the per-task OTel span's own context (format(ctx.trace_id,'032x')), NOT a free-standing langfuse.create_trace_id(). This makes 'trace_id non-None' and 'worker spans root under the inbound trace' the SAME id — divergent ids would break one assertion."
  - "run_mesh and resume_mesh both wrap their ENTIRE body in _task_root_span and set trace_id on EVERY return. resume_mesh has 3 return points (stub / no-checkpoint / durable-resume); in CI with no DATABASE_URL the no-checkpoint branch (line ~352) is taken, so setting trace_id only on the durable-resume return would leave it None there."
  - "approvals._approval_span passes client_slug from get_settings() and entrypoint='approval' to trace_metadata() (which has no defaults for those two). The approval-decision span fires in a SEPARATE /v1/approvals request from the model/tool spans, so it correlates by task_id, not the in-process traceparent — consistent with the threat model."
  - "Stale Phase-2 assertion test_orchestration_graph::test_stub_fallback 'trace_id is None # Langfuse correlation is Phase 3' updated to 'trace_id is set (32-hex)' — OBS-01 (this plan) is Phase 3 and the must_haves explicitly close that P2 gap (Rule 1 fix)."
metrics:
  duration_min: 34
  completed: 2026-06-06
  tasks: 3
  files_changed: 9
  commits: 4
  tests_added: 13
  default_suite: "118 passed, 6 skipped, 2 deselected"
---

# Phase 3 Plan 03: Langfuse + OTel Observability Summary

OBS-01 and OBS-02 landed locally: the dead langfuse v2 import (`langfuse.callback`)
is migrated to the v4 OTel-native path (`langfuse.langchain`); model/tool/approval
events now emit OTel spans carrying the shared request metadata under one per-task
`trace_id`; the inbound W3C `traceparent` is stored at the REAL `/v1/tasks` ingress
and restored in the worker so worker spans join the ingress trace across the Pub/Sub
boundary; and OBS-02 prompt-version + dataset + example-eval seeding is wired with a
trusted offline fallback — all while the default `make test` stays green with no
cloud deps.

## What Was Built

1. **v2→v4 migration + OTel `init_tracing` (Task 1, `feat`)** — Replaced the dead
   `from langfuse.callback import CallbackHandler` (a `ModuleNotFoundError` silently
   swallowed under langfuse 4.x → no traces, no error) with the v4
   `from langfuse.langchain import CallbackHandler`. Added `init_tracing(settings,
   test_exporter=)` building an OTel `TracerProvider` (`service.name=agent-mesh-worker`):
   an `InMemorySpanExporter` via `SimpleSpanProcessor` for CI (no server) else a
   `BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))`
   with Langfuse as the default consumer and a clearly-commented **parallel-SIEM seam**
   (D-07). Added `tracing_available()`, `set_span_metadata()`, `extract_otel_context()`,
   `span_trace_id()`, and `get_prompt_with_fallback()`. Every otel/langfuse import is
   lazy — the module stays importable with neither installed (degradation preserved).

2. **Span emission + trace_id + real-ingress traceparent store→restore (Task 2, TDD)** —
   - **STORE (api/app.py):** `POST /v1/tasks` injects the FastAPI `Request` under a
     distinct `http_request` name (no body-param collision; `Request` already imported),
     reads `traceparent`, and writes `request.metadata["traceparent"]` BEFORE
     `create_task()`. `TaskService` copies `request.metadata` onto the durable
     `TaskRecord`, so the value reaches the record (no schema change).
   - **RESTORE (orchestrator.py):** `run_mesh`/`resume_mesh` wrap their bodies in
     `_task_root_span`, which restores the stored traceparent as the OTel parent context
     (`TraceContextTextMapPropagator().extract`) so worker spans join the ingress trace,
     sets `trace_metadata()` keys as span attributes, and yields the span's trace id.
     `OrchestrationResult.trace_id` is SET on EVERY return (run + all 3 resume branches),
     closing the P2 gap.
   - **graph.py callback:** `_graph_config` attaches the v4 `CallbackHandler` via
     `config={"callbacks":[handler]}` (None-safe) so node/model spans nest under the
     task trace.
   - **approvals.py:** `open_approval`/`record_decision` wrapped in a READ-ONLY
     `_approval_span` carrying `trace_metadata()` attrs — telemetry only; `verify_approval_token`/
     `payload_hash`/`is_approved`/replay guard untouched, approver still derived solely
     from the signed token (RF-1 / SEC-01/02).

3. **Prompt fetch-with-fallback + live-lane seed (Task 3, `feat`)** —
   `get_prompt_with_fallback(name, local_default)` pulls a versioned prompt from Langfuse
   when reachable, else returns the trusted local default (offline-safe, anti-injection).
   `tests/test_langfuse_prompts.py` (default lane) proves the offline fallback three ways
   (no creds / langfuse unavailable / fetch raises). `tests/test_langfuse_seed_live.py`
   (`@pytest.mark.live` + a langfuse-creds skip gate) seeds ≥1 versioned prompt
   (`create_prompt(labels=["production"])`), one dataset (`create_dataset` +
   `create_dataset_item`), and one EXAMPLE eval (`create_score`) — proving the path
   without a real scoring engine (SI-01 deferred to Phase 4, D-08).

## Verification Evidence

- `make test` (default lane, `-m "not live"`): **118 passed, 6 skipped, 2 deselected** —
  master invariant holds with no provider/Postgres/Langfuse credentials.
- New tests: `test_observability_otel.py` (7), `test_trace_propagation.py` (3),
  `test_langfuse_prompts.py` (3) all pass; `test_langfuse_seed_live.py` (2) SKIP cleanly
  under `-m live` without Langfuse creds.
- **OBS-01 dead-import gate:** `grep -vE '^[[:space:]]*#' src/agent_mesh/observability.py
  | grep -c 'from langfuse.callback import'` returns **0** (non-comment lines); the v4
  `from langfuse.langchain import CallbackHandler` is present.
- **OBS-01 store→restore (not in-process):** `test_ingress_persists_inbound_traceparent_on_task_record`
  POSTs via a real FastAPI `TestClient` with a `traceparent` header and asserts the
  persisted `TaskRecord.metadata["traceparent"]` equals that header;
  `test_worker_restores_traceparent_and_joins_ingress_trace` asserts the worker's root
  span carries the SAME 32-hex trace id as the inbound header.
- **OBS-01 trace_id both paths:** `test_stub_run_emits_root_span_with_shared_metadata`
  (run) and `test_resume_run_sets_trace_id` (resume) assert `trace_id` non-None and
  equal to the emitted span's trace.
- **OBS-01 token/cost correlation:** the per-task root span carries `task_id` (asserted
  in `test_stub_run_...`), the same key the 03-01 `budget_ledger` rows are keyed by — so
  token/cost is correlatable to the task trace under shared metadata (the model/cost span
  itself rides on the live-lane `success_callback:[langfuse,otel]`; in CI the `_delegate`
  path is creds-gated `# pragma: no cover`).
- **SEC-01/02 phase gate:** `tests/test_approval_security.py` stays GREEN — the approval
  spans are read-only telemetry; no code branches on span data.
- `ruff check src/agent_mesh tests`: clean.

## Threat Register Outcomes

| Threat ID | Disposition | Evidence |
|-----------|-------------|----------|
| T-03-03-01 (approval span as trust signal) | mitigated | `_approval_span` is read-only; approver from signed token; SEC suite green; no branch on span data |
| T-03-03-02 (key/prompt-body leak into spans) | mitigated | `set_span_metadata` writes ONLY known `trace_metadata()` keys (correlation ids), skips None; no creds/prompt bodies as attributes |
| T-03-03-03 (cross-tenant trace correlation) | mitigated | every span carries `tenant_id`; `trace_id` is per-task; reads stay tenant-scoped |
| T-03-03-04 (prompt-injection via fetched prompt) | mitigated | `get_prompt_with_fallback` returns a trusted local default offline; live prompts are operator-curated versioned prompts |
| T-03-03-05 (untrusted OTLP endpoint) | accept | endpoint is operator-configured (settings); default suite uses in-memory exporter (no network) |
| T-03-03-06 (forged traceparent poisons correlation) | accept | telemetry-only — parents spans, never gates a decision; malformed values fall back to a fresh root (no crash) |

## Deviations from Plan

### Auto-fixed / Implementation Adjustments

**1. [Rule 1 - Bug] Stale Phase-2 assertion superseded by OBS-01.**
- **Found during:** Task 2 GREEN (full-suite run).
- **Issue:** `test_orchestration_graph::test_stub_fallback` asserted `read_result.trace_id
  is None  # Langfuse correlation is Phase 3`. This plan IS Phase 3, and the must_haves
  state "OrchestrationResult.trace_id is SET per task (closes the P2 gap)". The assertion
  became a false negative the moment OBS-01 wired trace_id.
- **Fix:** Updated to `trace_id is not None` + `len == 32` (the OBS-01 invariant). The
  trace_id is non-None in the default suite because OTel is installed (03-01 pins), so
  `get_tracer()` builds a process provider and spans get a real trace context.
- **Files:** `tests/test_orchestration_graph.py`. **Commit:** 68f7a3c.

**2. [Rule 3 - Blocking] `_approval_span` rewritten as a `@contextmanager` generator.**
- **Found during:** Task 2 GREEN.
- **Issue:** The first cut returned `tracer.start_as_current_span(name)` after manually
  calling `cm.__enter__()`, then returned the CM for the caller's `with`. OTel's
  `_AgnosticContextManager.__enter__` is not re-entrant that way and raised
  `AttributeError: '_AgnosticContextManager' object has no attribute 'args'` — breaking
  the SEC suite.
- **Fix:** Rewrote `_approval_span` as a `@contextmanager` generator that opens the span
  inside a single `with` and yields it (no-op `yield None` when OTel unavailable). SEC
  suite back to green.
- **Files:** `src/agent_mesh/services/approvals.py`. **Commit:** 68f7a3c.

**3. [Design seam, not a deviation] No-global-provider OTel injection.**
- The plan's verify runs 3 test files in one pytest process. `set_tracer_provider` is
  install-once-per-process, so a global provider would leak spans across files (the 2nd
  exporter would see zero spans). `init_tracing` therefore returns a provider WITHOUT
  installing it globally, and a `set_tracer_provider_override` test seam injects a
  per-test provider. Production uses a process-cached provider built once.

### Intentionally Deferred (per plan)

- The optional `make seed-langfuse` one-shot was NOT added — `make test-live` (from 03-01)
  already runs the live lane, and adding a Makefile target would touch a shared file
  without benefit. The seed runs via `pytest tests/test_langfuse_seed_live.py -m live`.
- No real LLM-judge scoring engine — the example eval is a single `create_score` call
  proving the path; the judge harness is Phase 4 / SI-01 (D-08).
- The OTLP endpoint path (`{host}/api/public/otel/v1/traces`) is a SETTING value, not a
  structural constant — it becomes live-lane runtime config in Phase 5 (DEP).

## Known Stubs

None that block OBS-01/OBS-02. The creds-present `_delegate` model-span path stays
`# pragma: no cover` (needs live creds), consistent with 03-01; the in-memory exporter
and tracer-provider override are intentional test seams, not production stubs.

## Self-Check: PASSED

- Created files verified present: `tests/test_observability_otel.py`,
  `tests/test_trace_propagation.py`, `tests/test_langfuse_prompts.py`,
  `tests/test_langfuse_seed_live.py`, `03-03-SUMMARY.md`.
- All 4 task commits verified in git log: `db6147e` (Task 1 feat), `e087a12`
  (Task 2 test/RED), `68f7a3c` (Task 2 feat/GREEN), `4fe1997` (Task 3 feat).
- TDD gate sequence present for Task 2: `test(...)` RED (`e087a12`) precedes its
  `feat(...)` GREEN (`68f7a3c`).
