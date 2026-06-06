---
phase: 03-model-gateway-observability
plan: 03
type: execute
wave: 2
depends_on: ["03-01"]
files_modified:
  - src/agent_mesh/observability.py
  - src/agent_mesh/api/app.py
  - src/agent_mesh/worker/orchestrator.py
  - src/agent_mesh/worker/graph.py
  - src/agent_mesh/services/approvals.py
  - tests/test_observability_otel.py
  - tests/test_trace_propagation.py
  - tests/test_langfuse_prompts.py
  - tests/test_langfuse_seed_live.py
autonomous: true
requirements: [OBS-01, OBS-02]
must_haves:
  truths:
    - "The dead langfuse v2 import (from langfuse.callback import CallbackHandler) is replaced with the v4 path (from langfuse.langchain import CallbackHandler); pyproject pin is langfuse>=4,<5 (fixed in 03-01)"
    - "init_tracing(settings, *, test_exporter=None) builds an OTel TracerProvider: InMemorySpanExporter for CI (no server) else OTLP-HTTP to settings.otel_exporter_otlp_endpoint (Langfuse = default consumer) with a parallel-SIEM exporter seam (D-07)"
    - "Model, tool, AND approval events emit OTel spans carrying the shared request metadata (trace_metadata() dict) as span attributes — correlated under shared metadata / task_id (OBS-01); model/tool spans additionally share one trace via the restored traceparent, while the approval-decision span (separate /v1/approvals request) correlates by task_id"
    - "OrchestrationResult.trace_id is SET per task (closes the P2 gap); the dataclass shape stays stable for runner/ledger/tests"
    - "The inbound W3C traceparent header is read at the REAL ingress (/v1/tasks in api/app.py) into TaskRequest.metadata['traceparent'] BEFORE create_task(), copied onto TaskRecord.metadata (task_service line 51), then restored in the worker so worker model/tool spans join the trace started at ingress across the Pub/Sub boundary (OTel context does NOT cross Pub/Sub). Cross-Pub/Sub correlation is proven via the ingress store path + worker restore, NOT a pure in-process round-trip"
    - "Langfuse prompt fetch-with-fallback returns the local default offline (make test green); ≥1 versioned prompt + one seeded dataset + an example/trivial eval are registered in the live lane only (OBS-02 / D-08)"
    - "Approval spans are READ-ONLY telemetry: SEC-01/SEC-02 (signed token, payload-hash, replay guard) are NOT weakened; no code branches on span data (RF-1)"
  artifacts:
    - path: "src/agent_mesh/observability.py"
      provides: "v4 CallbackHandler import; init_tracing() OTel provider + in-memory/OTLP exporter + SIEM seam; get_prompt_with_fallback(); trace_metadata reused as span attrs"
      contains: "from langfuse.langchain import CallbackHandler"
    - path: "src/agent_mesh/api/app.py"
      provides: "REAL ingress write of inbound W3C traceparent header into TaskRequest.metadata['traceparent'] before create_task() (closes the cross-Pub/Sub store-side gap)"
      contains: "traceparent"
    - path: "src/agent_mesh/worker/orchestrator.py"
      provides: "OrchestrationResult.trace_id SET in _run_langgraph and resume_mesh (was unset in P2); restores task.metadata['traceparent'] before opening the root span"
      contains: "trace_id"
    - path: "src/agent_mesh/worker/graph.py"
      provides: "langfuse v4 CallbackHandler attached via config={'callbacks':[handler]} on the graph run; model spans rooted under the task trace_id"
      contains: "callbacks"
    - path: "src/agent_mesh/services/approvals.py"
      provides: "read-only OTel approval span carrying trace_metadata() attrs; SEC-01/02 untouched"
      contains: "trace_metadata"
    - path: "tests/test_observability_otel.py"
      provides: "OBS-01: InMemorySpanExporter asserts spans + shared-metadata attrs; trace_id set on result"
      contains: "get_finished_spans"
    - path: "tests/test_trace_propagation.py"
      provides: "OBS-01: inbound traceparent header at /v1/tasks is persisted to TaskRecord.metadata and restored in worker → one trace (real store→restore, not in-process round-trip)"
      contains: "traceparent"
    - path: "tests/test_langfuse_prompts.py"
      provides: "OBS-02: get_prompt_with_fallback returns local default offline (green)"
      contains: "get_prompt_with_fallback"
    - path: "tests/test_langfuse_seed_live.py"
      provides: "OBS-02 live lane: seed ≥1 versioned prompt + dataset + example eval against real Langfuse"
      contains: "pytest.mark.live"
  key_links:
    - from: "src/agent_mesh/api/app.py"
      to: "TaskRequest.metadata['traceparent']"
      via: "reads inbound W3C traceparent header at /v1/tasks and stores it before create_task() (task_service copies metadata onto TaskRecord)"
      pattern: "traceparent"
    - from: "src/agent_mesh/worker/orchestrator.py"
      to: "OrchestrationResult.trace_id"
      via: "set from the per-task OTel root (langfuse.create_trace_id / get_current_trace_id), restoring task.metadata['traceparent'] first"
      pattern: "trace_id ="
    - from: "src/agent_mesh/services/approvals.py"
      to: "src/agent_mesh/observability.py"
      via: "read-only span with trace_metadata() attrs (never branches on span)"
      pattern: "trace_metadata"
    - from: "src/agent_mesh/worker/graph.py"
      to: "langfuse.langchain.CallbackHandler"
      via: "config={'callbacks':[handler]} on graph invocation"
      pattern: "callbacks"
---

<objective>
Wire the observability plane: OTel-first tracing transport with Langfuse as the default required OTLP
consumer (OBS-01), and Langfuse-native prompt/version + dataset/eval seeding (OBS-02).

THE URGENT FIX (RESEARCH Pitfall 2): `observability.py` line 76 imports `from langfuse.callback import
CallbackHandler` — a DEAD module under the installed langfuse 4.7.1 (`ModuleNotFoundError`), silently
swallowed by the except at line 83 → no traces, no error. The v4 path is `from langfuse.langchain import
CallbackHandler`. The pin (`langfuse>=4,<5`) is corrected in 03-01; this plan migrates the code. Langfuse
v4 is OTel-native (a thin layer over an OTel TracerProvider) — exactly what D-07's "OTel-first, Langfuse
as default OTLP consumer, pluggable + parallel SIEM" wants.

OBS-01/OBS-02 SPLIT (D-07): OTel covers the tracing TRANSPORT (OBS-01) — spans for model/tool/approval
events carrying the shared request metadata, one trace_id per task, cross-process traceparent
propagation. OBS-02 (prompt/version + datasets/evals) is Langfuse-NATIVE — OTel does not cover it.

THE CROSS-PROCESS SEAM (RESEARCH Pitfall 4): the worker's model/tool spans fire AFTER Pub/Sub (DUR-03),
separated from the trace started at the API ingress. OTel ambient context does NOT cross that boundary —
the inbound W3C `traceparent` HTTP header must be read at the REAL ingress (`/v1/tasks` in `api/app.py`)
and stored on `TaskRequest.metadata["traceparent"]` BEFORE `create_task()` (the shared `TaskService`
copies `request.metadata` onto the durable `TaskRecord`, task_service.py line 51), then restored in the
worker before the root span — or worker spans land in a SEPARATE trace and OBS-01 cross-Pub/Sub
"correlate" fails. The store side is the leg the prior plan left unwired; this revision names the real
ingress file and proves the store→restore round-trip end-to-end, NOT in-process.

Purpose: OBS-01 + OBS-02 — every model/tool/approval event correlates under shared metadata; prompt/eval configured.
Output: v4 migration + OTel init + trace_id wiring + REAL-ingress traceparent store + worker restore + prompt fetch-with-fallback + live seed.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@CLAUDE.md
@.planning/phases/03-model-gateway-observability/03-CONTEXT.md
@.planning/phases/03-model-gateway-observability/03-RESEARCH.md
@.planning/phases/03-model-gateway-observability/03-PATTERNS.md
@.planning/phases/03-model-gateway-observability/03-01-litellm-router-budget-PLAN.md

<interfaces>
<!-- Reuse as-is -->
observability.trace_metadata(tenant_id, client_slug, task_id, session_id, requester_id, entrypoint,
  agent_role, model_route_profile, approval_state) -> dict   (observability.py 38-62 — span attr source)
observability.langfuse_available() (29-35)   # mirror this gate shape for tracing_available()
<!-- REAL ingress seam (VERIFIED) -->
api/app.py: POST /v1/tasks -> create_task(request: TaskRequest) -> _service.create_task(request) (line 40-43);
  fastapi.Request already imported (line 19) — inject as a distinct param name to avoid colliding with `request` body
task_service.TaskService.create_task copies request.metadata -> TaskRecord(metadata=request.metadata) (line 51)
contracts/models.py: TaskRequest.metadata (line 77) and TaskRecord.metadata (line 99) are both dict[str, Any]
  -> store metadata["traceparent"]; NO schema change needed
<!-- Built/added in 03-01 (do NOT re-add) -->
settings.otel_exporter_otlp_endpoint, settings.langfuse_host/public_key/secret_key
pyproject: langfuse>=4,<5 + opentelemetry-{api,sdk,exporter-otlp-proto-http}>=1.42 ; conftest InMemorySpanExporter fixture
<!-- langfuse v4 (venv 4.7.1, VERIFIED) -->
from langfuse.langchain import CallbackHandler      # v4 path (v2 langfuse.callback is DEAD)
Langfuse(public_key, secret_key, host, tracer_provider=, span_exporter=)
langfuse client: create_prompt, get_prompt, create_dataset, create_dataset_item, create_score,
  create_trace_id, get_current_trace_id
<!-- OTel (venv 1.42.1, VERIFIED) -->
opentelemetry.sdk.trace.TracerProvider ; BatchSpanProcessor ; Resource.create
opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter  (HTTP only — gRPC not installed)
opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter
<!-- Approval guardrails — do NOT weaken (approvals.py) -->
verify_approval_token (113-155, fails closed 129-130); payload_hash (41-45); is_approved (200-210); replay guard (138-139)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: langfuse v2→v4 migration + OTel init_tracing (OBS-01 transport)</name>
  <read_first>
    - src/agent_mesh/observability.py (FULL — langfuse_available 29-35; trace_metadata 38-62; get_langchain_callback dead v2 import line 76, except-swallow line 83)
    - .planning/phases/03-model-gateway-observability/03-RESEARCH.md (Finding 3; Pitfall 2; Pitfall 5; State of the Art; OTLP exporter note)
    - .planning/phases/03-model-gateway-observability/03-PATTERNS.md (observability.py section; lazy optional-dep import; stub-fallback degradation)
    - tests/conftest.py (InMemorySpanExporter fixture from 03-01)
  </read_first>
  <action>
    In `observability.py` replace `from langfuse.callback import CallbackHandler` (line 76) with
    `from langfuse.langchain import CallbackHandler` (v4 path), keeping the lazy-import + return-None-when-
    unavailable degradation (so the module stays importable without langfuse). Add
    `init_tracing(settings, *, test_exporter=None)` (lazy `from opentelemetry...` imports inside the function):
    build a `TracerProvider(resource=Resource.create({"service.name":"agent-mesh-worker","deployment.environment":
    settings.tenant_id}))`; when `test_exporter` is passed, add `BatchSpanProcessor(test_exporter)` (CI
    InMemorySpanExporter — no server); else add a `BatchSpanProcessor(OTLPSpanExporter(endpoint=
    settings.otel_exporter_otlp_endpoint, headers=...))` (Langfuse default consumer) and leave a clearly
    commented PARALLEL-SIEM SEAM where a second processor/exporter can be added without dropping Langfuse
    (D-07). Add `tracing_available()` mirroring `langfuse_available()`. Keep the exact Langfuse OTLP endpoint
    path (`{host}/api/public/otel/v1/traces`) as a SETTING value (A1 live-lane runtime decision) — do NOT
    hardcode it as a structural assumption. Add a helper that sets the `trace_metadata()` dict keys as span
    attributes on the root span.
  </action>
  <verify>
    <automated>python -c "import agent_mesh.observability as o; assert hasattr(o,'init_tracing'); assert 'langfuse.langchain' in open('src/agent_mesh/observability.py').read()" && test "$(grep -vE '^[[:space:]]*#' src/agent_mesh/observability.py | grep -c 'from langfuse.callback import')" -eq 0 && pytest tests/test_observability_otel.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - On non-comment lines (`grep -vE '^[[:space:]]*#'`), `grep -c 'from langfuse.callback import'` returns 0 AND the `from langfuse.langchain import CallbackHandler` import is present (positive + negative pair; comments referencing the old path are allowed)
    - `init_tracing(settings, test_exporter=mem)` wires the InMemorySpanExporter; no OTLP server contacted in CI
    - The OTLP branch targets `settings.otel_exporter_otlp_endpoint`; a parallel-SIEM seam is present and commented
    - Module imports cleanly with NO langfuse/otel installed (degradation preserved)
  </acceptance_criteria>
  <done>Dead v2 import gone; v4 OTel-native handler + configurable/in-memory OTel transport with a SIEM seam.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Span emission + trace_id + REAL-ingress traceparent store→worker restore (OBS-01 correlation)</name>
  <read_first>
    - src/agent_mesh/api/app.py (POST /v1/tasks create_task 39-43; fastapi.Request import line 19; body param named `request`)
    - src/agent_mesh/services/task_service.py (create_task 37-58 — copies request.metadata onto TaskRecord line 51)
    - src/agent_mesh/contracts/models.py (TaskRequest.metadata line 77; TaskRecord.metadata line 99 — both dict[str, Any])
    - src/agent_mesh/worker/orchestrator.py (_run_langgraph 200-243; OrchestrationResult 124-129; resume_mesh / stack path 300-306; trace_id unset 242/305)
    - src/agent_mesh/worker/graph.py (node bodies 84-135; _model_credentials_present 66-81; write_gate RF-1 138-167)
    - src/agent_mesh/services/approvals.py (open_approval 158-176; record_decision 179-197; verify_approval_token 113-155; is_approved 200-210; replay guard 138-139)
    - .planning/phases/03-model-gateway-observability/03-RESEARCH.md (Finding 3 coherence #5/#6; Pitfall 4; Security Domain V4/V6)
    - .planning/phases/03-model-gateway-observability/03-PATTERNS.md (orchestrator.py / graph.py / approvals.py sections)
  </read_first>
  <behavior>
    - Running a stub mesh task produces OTel spans (via InMemorySpanExporter) for the root + node events carrying tenant_id/task_id/session_id/requester_id/approval_state as span attributes
    - OrchestrationResult.trace_id is non-None after a run (both _run_langgraph and resume_mesh paths)
    - A POST to /v1/tasks carrying an inbound W3C `traceparent` header results in that exact value persisted on TaskRecord.metadata["traceparent"]; the worker reads it back and roots its spans under that trace (store→restore proven across the Pub/Sub boundary, NOT pre-populated in-process)
    - A task created WITHOUT a traceparent header still works (no KeyError) — the worker starts a fresh root trace
    - Approval span emission does NOT change approval semantics: a forged token still rejected, a mutated payload still invalidates, replay still blocked (SEC-01/02 tests stay green)
  </behavior>
  <action>
    REAL INGRESS STORE (closes the checker BLOCKER): in `api/app.py` `/v1/tasks`, inject the FastAPI request
    object under a DISTINCT name (e.g. `http_request: Request`) to avoid colliding with the `request:
    TaskRequest` body param — `Request` is ALREADY imported (line 19), no new import. Read
    `http_request.headers.get("traceparent")`; if present, set `request.metadata["traceparent"] = <value>`
    BEFORE `_service.create_task(request)`. No schema change: `metadata` is `dict[str, Any]` and
    `task_service.create_task` copies `request.metadata` onto `TaskRecord.metadata` (line 51), so the value
    reaches the durable record. WORKER RESTORE: in `orchestrator.py`, before opening the per-task root span,
    read `task.metadata.get("traceparent")` and, when present, build the OTel parent context from it (W3C
    propagator / extract) so the worker's spans join the ingress trace; when absent, start a fresh root.
    Then SET `OrchestrationResult.trace_id` (currently unset, lines 242/305) from the per-task OTel root
    (`langfuse.create_trace_id()` / `get_current_trace_id()`); keep the dataclass shape stable; set the
    `trace_metadata()` dict as span attributes on the root. In `graph.py`, attach the v4 CallbackHandler to
    the graph run via `config={"callbacks":[handler]}` (handler from `observability.get_langchain_callback`,
    None-safe) so node/model spans nest under the task trace. In `approvals.py` wrap `open_approval`/
    `record_decision` with a READ-ONLY OTel span carrying `trace_metadata()` attrs — the span is telemetry
    ONLY: do NOT branch on span data, do NOT alter `verify_approval_token`/`payload_hash`/`is_approved`/
    replay guard; the approver is derived solely from the signed token (RF-1 / SEC-01/02).
  </action>
  <verify>
    <automated>pytest tests/test_observability_otel.py tests/test_trace_propagation.py tests/test_approval_security.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_observability_otel.py` asserts `mem.get_finished_spans()` contains spans whose attributes include the shared-metadata keys (tenant_id, task_id, session_id, requester_id, approval_state)
    - `OrchestrationResult.trace_id` is non-None after a run (both paths)
    - `tests/test_trace_propagation.py` POSTs to `/v1/tasks` via a FastAPI TestClient with a `traceparent` HTTP header and ASSERTS the persisted `TaskRecord.metadata["traceparent"]` equals that header value (proves the REAL ingress store path), THEN asserts the worker restore roots its spans under that same trace — this is NOT a pre-populated in-process metadata dict
    - `tests/test_trace_propagation.py` also covers the no-header case: task creation and worker run succeed with a fresh root trace (no KeyError)
    - `tests/test_approval_security.py` (Phase-1 suite) stays GREEN — SEC-01/02 untouched (phase gate)
    - No code branches on span data (approver still from signed token)
    - OBS-01 token/cost clause: model token/cost correlates to the task trace — assert a model/cost span (or the budget_ledger row from 03-01) is keyed by the same task_id/trace_id as the root span, so token/cost is correlatable under the shared metadata (rides on yaml success_callback:[langfuse,otel] in the live lane + ledger cost keyed by task_id)
  </acceptance_criteria>
  <done>Model/tool/approval events correlate under one trace_id; the inbound traceparent is stored at the real ingress and restored in the worker (store→restore proven, not in-process); SEC-01/02 intact.</done>
</task>

<task type="auto">
  <name>Task 3: Langfuse prompt fetch-with-fallback + live-lane seed (OBS-02 / D-08)</name>
  <read_first>
    - src/agent_mesh/observability.py (langfuse_available 29-35; v4 client surface added in Task 1)
    - .planning/phases/03-model-gateway-observability/03-RESEARCH.md (Finding 7; D-08; "OBS-02 is Langfuse-native / live-lane only")
    - .planning/phases/03-model-gateway-observability/03-PATTERNS.md (No Analog Found: langfuse v4 prompt fetch-with-fallback + dataset/eval seed)
    - tests/conftest.py (live-marker skip fixture from 03-01)
  </read_first>
  <action>
    In `observability.py` add `get_prompt_with_fallback(name, local_default)`: try
    `get_client().get_prompt(name).prompt` (pulls the versioned prompt from Langfuse when reachable), else
    return `local_default` (keeps `make test` green offline — the stub-fallback invariant). Create
    `tests/test_langfuse_prompts.py` (default lane) asserting `get_prompt_with_fallback` returns the local
    default when Langfuse is unreachable/uninstalled. Create `tests/test_langfuse_seed_live.py` (every test
    `@pytest.mark.live`, gated on the live-creds skip fixture): register ≥1 versioned prompt via
    `create_prompt(name=..., prompt=..., labels=["production"])`, seed one dataset via
    `create_dataset(name="phase3-seed")` + `create_dataset_item(...)` (input/expected_output from task
    evidence), and register an EXAMPLE/TRIVIAL eval via `create_score(...)` on a dataset run to prove the path.
    Do NOT build a real scoring engine — the LLM-judge harness is Phase 4 / SI-01 (D-08). Optionally add a
    `make seed-langfuse` one-shot for the live seed.
  </action>
  <verify>
    <automated>pytest tests/test_langfuse_prompts.py -x -q && (pytest tests/test_langfuse_seed_live.py -m live -q || echo "SKIPPED-WITHOUT-CREDS (expected in default CI)")</automated>
  </verify>
  <acceptance_criteria>
    - `get_prompt_with_fallback` returns the local default offline; `tests/test_langfuse_prompts.py` passes with no Langfuse creds
    - `tests/test_langfuse_seed_live.py` tests carry `@pytest.mark.live` and SKIP cleanly without creds
    - With creds: ≥1 versioned prompt + one dataset + one example eval are registered against real Langfuse
    - No real scoring engine added (SI-01 not pulled forward)
  </acceptance_criteria>
  <done>OBS-02 prompt/version + dataset + example eval are seeded (live lane) with an offline fallback; default suite green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| inbound HTTP (traceparent header) → /v1/tasks | untrusted header read into task metadata; telemetry-only, never a trust signal |
| ingress (trace started) → worker (model spans) | crosses Pub/Sub; correlation via stored→restored traceparent on the task record |
| worker → Langfuse OTLP / parallel SIEM | spans + token/cost exported; must not carry secrets |
| Langfuse-fetched prompt → agent | externally-fetched content used as a prompt |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-03-01 | Elevation of Privilege | approval span treated as a trust signal | mitigate | span is read-only telemetry; approver derived solely from signed token (SEC-01); never branch on span data (RF-1, Task 2) |
| T-03-03-02 | Information Disclosure | provider/Langfuse keys or full prompt bodies leak into spans | mitigate | never set api_key/raw creds as span attributes; only shared-metadata keys; CF owns body-DLP; keys from env (Task 1/2) |
| T-03-03-03 | Information Disclosure | cross-tenant trace correlation (one tenant sees another's spans) | mitigate | shared metadata includes tenant_id on every span; trace_id is per-task; reads stay tenant-scoped (DUR-02) |
| T-03-03-04 | Tampering | prompt-injection via a Langfuse-fetched prompt | mitigate | fetch-with-fallback returns a trusted local default offline; live-fetched prompts are operator-curated versioned prompts (D-08), not user input; RF-1 write-gate still gates all writes |
| T-03-03-05 | Spoofing | untrusted OTLP endpoint receiving spans | accept | endpoint is operator-configured (settings); live-lane only; default suite uses in-memory exporter (no network) |
| T-03-03-06 | Tampering | forged inbound traceparent header poisons trace correlation | accept | traceparent is telemetry-only — it parents spans, never gates a decision or grants authority; malformed values fall back to a fresh root trace (no crash); no security control reads it |
</threat_model>

<verification>
- `make test` GREEN with NO cloud deps: `test_observability_otel.py`, `test_trace_propagation.py`, `test_langfuse_prompts.py` pass; `test_langfuse_seed_live.py` SKIPS.
- `tests/test_approval_security.py` (Phase-1) stays green — SEC-01/02 not weakened (phase gate).
- `grep -vE '^[[:space:]]*#' src/agent_mesh/observability.py | grep -c 'from langfuse.callback import'` == 0 (dead v2 import statement gone; non-comment lines only).
- `tests/test_trace_propagation.py` proves the REAL ingress store path (TestClient POST with traceparent header → persisted TaskRecord.metadata) plus worker restore — not an in-process round-trip.
- `make test-live` runs the Langfuse seed with user creds (opt-in); default suite never requires `-m live`.
</verification>

<success_criteria>
OBS-01 and OBS-02 are locally provable: OTel spans for model/tool/approval events correlate under one
per-task trace_id with shared metadata (in-memory exporter, no server), the inbound traceparent is stored
at the real /v1/tasks ingress and restored in the worker so worker spans join the ingress trace across
Pub/Sub, the dead langfuse v2 import is fixed, and prompt/version + dataset + example eval are seeded —
default suite green, live lane opt-in.
</success_criteria>

<output>
Create `.planning/phases/03-model-gateway-observability/03-03-SUMMARY.md` when done.
</output>
</content>
</invoke>
