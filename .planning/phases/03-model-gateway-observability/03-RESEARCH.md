# Phase 3: Model Gateway & Observability - Research

**Researched:** 2026-06-06
**Domain:** Live LiteLLM model control plane (in-process Router) + OTel/Langfuse observability plane, on the existing LangChain/LangGraph/Deep Agents POC scaffold
**Confidence:** HIGH (every load-bearing claim verified against the project's own `.venv` — installed package introspection, not training data)

> **Provenance note.** All version pins, API shapes, and import paths below are tagged
> `[VERIFIED: .venv introspection]` where I ran the installed package in
> `./.venv/bin/python`. The `.venv` already contains the full runtime+agents stack
> (litellm 1.83.7, langfuse 4.7.1, langchain-litellm 0.6.4, langchain 1.3.4,
> langgraph 1.2.4, deepagents 0.6.8, opentelemetry 1.42.1). Package *names* originate
> from the project's own `pyproject.toml` (authoritative, already in-repo), so they are
> not third-party-discovery `[ASSUMED]` names.

---

<user_constraints>
## User Constraints (from 03-CONTEXT.md)

### Locked Decisions (D-01..D-09 — research must not contradict)
- **D-01: Real Router → Real Provider is the live proof.** No faked provider boundary. A
  faked/mock provider boundary was explicitly REJECTED. "Live" = a genuine `litellm.Router`
  calling real Anthropic and real Vertex AI.
- **D-02: Opt-in live lane.** Default `make test` / `make smoke` stay on the deterministic
  stub path (green, no creds, CI-safe). A separate marked lane (`make test-live` /
  `pytest -m live`) drives real router → real providers with the user's keys + a tiny (cents)
  budget cap.
- **D-03: Both providers live.** The live lane makes real calls to **both** Anthropic-direct
  and Vertex AI. GW-03 cross-provider cascade = Vertex primary → real failure → Anthropic
  fallback. A live Vertex *model call* is NOT GCP provisioning (no Cloud SQL / Cloud Run).
- **D-04: Durable ledger halts; gateway backs in prod.** Durable `budget_ledger` (Postgres,
  tenant-scoped) is the local-provable enforcement point: pre-call `check()` reads
  month-to-date → raises `BudgetExceeded` → run halts cleanly + a `gateway_event` recorded;
  post-call `record()` persists actual cost. **In the D-09 in-process Router runtime the
  durable ledger is the SOLE budget enforcer** — this IS the GW-01 gateway control-plane
  enforcement. `general_settings.max_budget:50` is inert in the POC runtime; asserted by
  config only.
- **D-05: Per-user halts; per-task attributes.** `$50/month per-user` (budget_owner) is the
  hard cap that halts. Per-task = cost attribution: every row tagged with `task_id`, with an
  optional `per_task_cap` defaulting to the per-user cap.
- **D-06: Structural egress chokepoint + config assertion.** ALL model construction flows
  through `model_gateway.get_chat_model()`, which always sets `api_base` to the gateway /
  CF-wrapper URL. A guard test fails if any path builds a provider client without it. A
  config test asserts every route's `api_base` = CF wrapper when CF enabled. Real CF
  traversal is opt-in (`CF_AIG_WRAPPER_URL` set); CF-disabled is a valid POC state.
- **D-07: OTel-first; Langfuse = default/required consumer; pluggable + parallel SIEM.**
  Model, tool, AND approval events emit OpenTelemetry spans with shared request metadata as
  span attributes. A single `trace_id` per task is set on `OrchestrationResult` (closes the
  P2 gap). Spans export via OTLP to a configurable endpoint; Langfuse is the default OTLP
  consumer and stays REQUIRED. "Replaceable / parallel" does NOT make Langfuse optional. CI
  proof = an in-memory OTel span exporter; live lane exports to real Langfuse.
  **OBS-01/OBS-02 split:** OTel covers tracing transport (OBS-01). OBS-02 (prompt/version +
  datasets/evals) is Langfuse-native — OTel does not cover it.
- **D-08: Thin / seeded observability prompt/eval.** Wire Langfuse prompt/version management
  with local fetch-with-fallback, register ≥1 versioned prompt, seed one dataset, register
  an example/trivial eval. The real eval harness (scoring engine) is Phase 4 (SI-01).
- **D-09: In-process `litellm.Router` is the POC runtime; standalone proxy is a
  deploy-validated scale-up path.** A loader builds a real `litellm.Router` from
  `config/model_gateway.config.yaml`; cascades + retries run in-process. `get_chat_model()`
  returns a Router-backed model. Proxy-only yaml fields (`master_key`,
  `general_settings.max_budget`) are prod-proxy config asserted structurally, not executed.

### Claude's Discretion (research recommends)
- `gateway_events` table schema/shape + reuse-vs-new migration → **RESOLVED: tables already
  exist** (see Finding 5).
- Exact `litellm.Router` load/construction + how `langchain_litellm`/`ChatLiteLLM` binds to an
  in-process Router → **RESOLVED** (Finding 1).
- Token-cost estimation method for pre-call `check()` → **RESOLVED** (Finding 2).
- OTel exporter/config surface (resource attrs, OTLP endpoint env, multi-exporter fan-out) →
  **RESOLVED** (Finding 3).
- Cross-provider cascade trigger mechanics for GW-03 → **RESOLVED** (Finding 4).

### Deferred Ideas (OUT OF SCOPE — ignore)
- Standalone LiteLLM proxy server runtime (centralized cross-worker budget, key isolation, HA).
- `wrangler` publish / dry-run of the CF worker + true idempotency → Phase 5 / DEP-02.
- Real evaluation harness (LLM-judge scoring engine) → Phase 4 / SI-01.
- Live GCP infra provisioning (Cloud SQL / Cloud Run / Secret Manager) → v2 (DEP-03/04).
- Data-residency enforcement (model processing may leave AU for the POC).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GW-01 | Live LiteLLM-compatible gateway routes to Anthropic-direct + Vertex AI with cascades and enforces USD $50/mo per-user/per-task budget | Finding 1 (in-process Router build+bind) + Finding 2 (durable-ledger budget enforcement, the D-04 control plane) + Finding 5 (budget_ledger persistence) |
| GW-02 | Gateway routes all upstream calls through CF AI Gateway when enabled; agents never call providers directly | Finding 1 (Router `model_list` per-route `api_base`) + Finding 6 (D-06 guard test relocation) |
| GW-03 | Failure test proves model fallback + budget-limit halt | Finding 4 (two-lane cascade trigger: `mock_testing_fallbacks` stub lane + real Vertex failure live lane) + Finding 2 (clean budget halt) |
| OBS-01 | Langfuse telemetry: spans, token/cost, task/tool/approval events correlate via shared request metadata | Finding 3 (OTel→Langfuse v4 OTLP-native transport, in-memory CI exporter, cross-process trace propagation) |
| OBS-02 | Langfuse prompt/version management + datasets/evals configured | Finding 7 (langfuse v4 prompt/dataset/eval API surface; D-08 thin/seeded) |
</phase_requirements>

## Summary

Phase 3 is mechanically smaller than it looks because **the data layer is already built**:
`migrations/0001_init.sql` already contains the `budget_ledger` and `gateway_events` tables
(verified, lines 201-229), and `contracts/models.py` already defines the matching `BudgetEvent`
and `GatewayEvent` Pydantic models. The schema research focus (#5) is effectively done — the
real work there is *adding repository methods*, not a new migration.

The phase has **two genuinely tricky seams** and **one urgent dependency-drift problem**:

1. **In-process Router binding (D-09/Focus #1).** `langchain_litellm.ChatLiteLLM`'s pydantic
   validator **unconditionally clobbers** any user-supplied `client` with the bare `litellm`
   module (`values["client"] = litellm`, litellm.py:558). You therefore cannot just pass
   `client=Router(...)`. The clean fix is a **thin `ChatLiteLLM` subclass** that holds the
   Router and overrides `completion_with_retry`/`acompletion_with_retry` to call
   `self._router.completion(...)`. `Router.completion(model, messages, **kwargs)` is
   signature-compatible with `litellm.completion`, so the swap is exact.

2. **Langfuse v2→v4 break (urgent).** `pyproject.toml` pins `langfuse>=2.0`, but the `.venv`
   has **langfuse 4.7.1**, and the v2 import in `observability.py`
   (`from langfuse.callback import CallbackHandler`) is **dead** under v4
   (`ModuleNotFoundError: No module named 'langfuse.callback'`). The v4 path is
   `from langfuse.langchain import CallbackHandler`. Langfuse v3+ is **OTel-native** — it is a
   thin layer over an OpenTelemetry `TracerProvider` — which is exactly what D-07's
   "OTel-first, Langfuse as default OTLP consumer" wants. This must be fixed in `observability.py`
   and `pyproject.toml` as part of this phase.

3. **Budget enforcement is a durable-ledger pre-call check**, not a LiteLLM feature, in the
   D-09 runtime. Pre-call estimate via `litellm.get_max_tokens` / `cost_per_token`; post-call
   actual via the provider-returned `usage` and `litellm.completion_cost`.

**Primary recommendation:** Build the in-process Router loader + a thin Router-backed
`ChatLiteLLM` subclass in `model_gateway.py`; migrate `observability.py` to langfuse v4's
OTel-native LangChain handler and a configurable OTLP/in-memory exporter; persist
`BudgetTracker` to the existing `budget_ledger`; relocate the D-06 guard from
`ChatLiteLLM.api_base` to the Router's per-deployment `model_list[*].litellm_params.api_base`.
Split GW-03 into a deterministic stub lane (`mock_testing_fallbacks`) and a live lane
(real Vertex failure → real Anthropic fallback).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Model routing / cascade / retry | In-process `litellm.Router` (worker) | CF AI Gateway (edge) | D-09: control plane is in-process Python; CF is the managed governance edge upstream |
| Budget enforcement (halt) | Durable `budget_ledger` (Postgres) | — | D-04: ledger is the SOLE enforcer in the in-process runtime; this IS GW-01's gateway control-plane enforcement |
| Model-traffic governance (DLP/logging/blocking) | CF AI Gateway (edge) | — | CLAUDE.md §3: CF owns governance; integration-ready this phase, not deployed |
| Tracing transport (spans, token/cost) | OTel SDK (worker + ingress) | OTLP exporter → Langfuse / parallel SIEM | D-07: vendor-neutral OTel-first; Langfuse default consumer |
| Prompt/version mgmt + datasets/evals | Langfuse SDK (native) | — | OBS-02 / D-08: OTel does not cover this; Langfuse-native only |
| Trace correlation root | `OrchestrationResult.trace_id` (worker) | task record `traceparent` (cross-process) | D-07: one trace_id per task; propagate across Pub/Sub boundary |

## Standard Stack

### Core (all already in `.venv` — verified)
| Library | Installed Version | pyproject pin (current) | Purpose | Action |
|---------|-------------------|--------------------------|---------|--------|
| `litellm` | **1.83.7** | `>=1.40` | In-process `Router` (routing/cascade/retry), cost helpers | Pin OK; keep `>=1.40` (1.83.7 satisfies) |
| `langchain-litellm` | **0.6.4** | `>=0.1` | `ChatLiteLLM` LangChain binding | Pin OK; bump floor to `>=0.6` to guarantee `client`/`completion_with_retry` shape |
| `langfuse` | **4.7.1** | `>=2.0` | **OTel-native** tracing + prompt/version + datasets/evals | **MUST bump to `>=4,<5`** — v2 path is dead (see State of the Art) |
| `langchain` | 1.3.4 | `>=1.0` (agents) | Tool/model abstraction | OK |
| `langgraph` | 1.2.4 | `>=1.0,<2` (agents) | Graph + callbacks config | OK |
| `deepagents` | **0.6.8** | `~=0.6.8` (agents) | Bounded roster harness | OK; pin is exact and matches venv |
| `opentelemetry-api` | **1.42.1** | **(absent)** | OTel span API | **ADD `opentelemetry-api>=1.42`** |
| `opentelemetry-sdk` | **1.42.1** | **(absent)** | TracerProvider, in-memory exporter | **ADD `opentelemetry-sdk>=1.42`** |
| `opentelemetry-exporter-otlp-proto-http` | **(absent — see note)** | (absent) | OTLP HTTP exporter to Langfuse / SIEM | **ADD `opentelemetry-exporter-otlp-proto-http>=1.42`** |

> **OTLP exporter note (VERIFIED).** The HTTP exporter module
> `opentelemetry.exporter.otlp.proto.http.trace_exporter` **imports cleanly** in the venv
> (it ships transitively), but the **gRPC** exporter
> (`opentelemetry.exporter.otlp.proto.grpc.trace_exporter`) is **NOT installed**. Pin the
> **HTTP** OTLP exporter explicitly (Langfuse's OTLP ingest is HTTP at `/api/public/otel`),
> do **not** pin the gRPC exporter. The in-memory exporter for CI
> (`opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter`) ships with
> `opentelemetry-sdk` — no extra dep.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-process `litellm.Router` | Standalone LiteLLM proxy server | D-09 REJECTS for the POC: a self-run proxy is a second self-operated SPOF in front of the managed CF edge. Proxy is the deploy-validated scale-up path only. |
| Thin `ChatLiteLLM` subclass holding a Router | `chat.client = router` post-construction reassignment | The post-hoc set "works" but is fragile: `_client_params` mutates `client.api_base/api_key/extra_headers` on every call (litellm.py:470-495). On a Router those sets are inert but undocumented; a subclass override is the durable choice (see Pitfall 1). |
| `langfuse.langchain.CallbackHandler` (v4) | LiteLLM `success_callback=["langfuse"]` only | Use BOTH but root them under one trace (see Finding 3 / coherence #5). The LangChain handler covers graph spans; LiteLLM's callback covers model spans. |

**Installation (pyproject `runtime` extra delta):**
```toml
runtime = [
    # ... existing ...
    "litellm>=1.40",                              # 1.83.7 in venv
    "langchain-litellm>=0.6",                     # was >=0.1 — bump for stable client shape
    "langfuse>=4,<5",                             # was >=2.0 — v2 import path is DEAD under v4
    "opentelemetry-api>=1.42",                    # NEW
    "opentelemetry-sdk>=1.42",                    # NEW
    "opentelemetry-exporter-otlp-proto-http>=1.42",  # NEW (HTTP, not gRPC)
]
```

## Package Legitimacy Audit

> All packages are already present in the project's `pyproject.toml` (in-repo, authoritative)
> and resolved into the project's `.venv`. No new third-party-discovered names introduced;
> the three OTel additions are official OpenTelemetry-Python packages already transitively
> present. slopcheck not run — packages are first-party-declared, not discovery candidates.

| Package | Registry | Installed | Source Repo | Disposition |
|---------|----------|-----------|-------------|-------------|
| litellm | PyPI | 1.83.7 | github.com/BerriAI/litellm | Approved (in-repo pin) |
| langchain-litellm | PyPI | 0.6.4 | github.com/Akshay-Dongare/langchain-litellm | Approved (in-repo pin) |
| langfuse | PyPI | 4.7.1 | github.com/langfuse/langfuse-python | Approved (in-repo pin; bump constraint) |
| opentelemetry-api | PyPI | 1.42.1 | github.com/open-telemetry/opentelemetry-python | Approved (official OTel) |
| opentelemetry-sdk | PyPI | 1.42.1 | github.com/open-telemetry/opentelemetry-python | Approved (official OTel) |
| opentelemetry-exporter-otlp-proto-http | PyPI | (transitively present, pin to install) | github.com/open-telemetry/opentelemetry-python | Approved (official OTel) |

## Architecture Patterns

### System Architecture Diagram (Phase 3 data + telemetry flow)

```
  ingress (API/Slack/MCP)                         worker (Cloud Run Job / in-process)
  ──────────────────────                          ────────────────────────────────────
  TaskRequest                                      run_mesh(task)
     │  emits approval span                            │
     │  (OTel, attrs=shared metadata)                  ▼
     │                                          LangGraph StateGraph (graph.py)
     ▼                                          planner→researcher→code_writer→reviewer→write_gate
  task record  ──[Pub/Sub: carries traceparent]──►     │  each node (creds present):
  (store traceparent +                                  ▼     get_chat_model(tier)
   trace_id)                                      ┌──────────────────────────────┐
                                                  │ RouterChatLiteLLM (subclass) │  D-06 chokepoint
                                                  │   .client = litellm.Router   │
                                                  └──────────────┬───────────────┘
                                                                 │ pre-call: budget.check() ──► budget_ledger (MTD read, tenant-scoped)
                                                                 │            └─ over cap ─► BudgetExceeded ─► clean halt + gateway_event
                                                                 ▼
                                            litellm.Router.completion(model, messages)
                                              model_list[tier].litellm_params.api_base = CF wrapper (when CF_ENABLED)
                                              router_settings.fallbacks → cascade in-process
                                                                 │
                                              ┌──────────────────┴───────────────────┐
                                              │ CF AI Gateway (edge, when enabled)    │  logging/DLP/guardrails
                                              └──────────────────┬───────────────────┘
                                                                 ▼
                                              Anthropic-direct  /  Vertex AI  (real providers, D-01)
                                                                 │ post-call: usage → budget.record() → budget_ledger
                                                                 ▼
                          OTel spans (model+tool+approval) ── OTLP HTTP ──► Langfuse (default consumer)
                            rooted at OrchestrationResult.trace_id                 └─► [optional] parallel SIEM exporter
                          CI: InMemorySpanExporter asserts spans+attrs (no server)
```

### Recommended file touch-map (extends, never replaces)
```
src/agent_mesh/worker/model_gateway.py   # + Router loader from yaml; + RouterChatLiteLLM subclass; get_chat_model returns it
src/agent_mesh/worker/budget.py          # BudgetTracker._spent dict → durable budget_ledger reads/writes (keep check/record/month_to_date API)
src/agent_mesh/observability.py          # v2→v4 langfuse import; + OTel TracerProvider/exporter setup; + in-memory exporter seam; keep importable-without-deps
src/agent_mesh/worker/graph.py           # node real-model delegation behind _model_credentials_present() (still stub-degrades)
src/agent_mesh/worker/orchestrator.py    # set OrchestrationResult.trace_id (D-07); keep dataclass shape stable
src/agent_mesh/services/approvals.py     # emit correlated OTel approval span (do NOT weaken SEC-01/02)
src/agent_mesh/services/repository.py    # + budget/gateway methods on Repository protocol, RepositorySQL, InMemoryRepository (tenant-scoped)
src/agent_mesh/settings.py               # + cf_aig_wrapper_url, cf_enabled, otel_exporter_otlp_endpoint, langfuse v4 host, model_per_task_cap
pyproject.toml                           # langfuse>=4,<5; +3 OTel deps; bump langchain-litellm>=0.6
config/model_gateway.config.yaml         # source of truth — loader reads model_list/router_settings/fallbacks/num_retries
# migrations/  — NO new migration needed: budget_ledger + gateway_events already exist in 0001_init.sql
```

### Anti-Patterns to Avoid
- **Passing `client=Router(...)` into `ChatLiteLLM(...)`** — the validator clobbers it (line 558). Use the subclass.
- **Relying on `general_settings.max_budget:50` to halt** — it is INERT in the in-process runtime (D-04/D-09). The durable ledger halts.
- **Asserting D-06 against `ChatLiteLLM.api_base`** — under the in-process Router, `api_base` lives per-route in `model_list[*].litellm_params.api_base`, not on the chat model (coherence #3).
- **Assuming OTel context crosses Pub/Sub** — it does not; you must carry `traceparent` in the task record (coherence #6).
- **Using `langfuse.callback.CallbackHandler`** — dead module under v4.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Model routing / cascade / retry | Custom try/except fallback loop | `litellm.Router(model_list=..., fallbacks=..., num_retries=...)` | Router executes cascades + retries in-process per D-09; battle-tested error classification |
| Pre-call token cost estimate | Hardcoded price tables | `litellm.get_max_tokens()`, `litellm.cost_per_token()`, `litellm.completion_cost()` | Verified present; litellm maintains the per-model price map |
| Post-call actual cost | Manual token math | provider-returned `usage` + `litellm.completion_cost(completion_response=...)` | Authoritative usage from the response |
| Span emission / OTLP transport | Custom HTTP span shipper | `opentelemetry-sdk` `TracerProvider` + `BatchSpanProcessor` + OTLP HTTP exporter | Vendor-neutral (D-07), supports multi-exporter fan-out natively |
| Deterministic CI span assertions | Mock/patch the exporter | `InMemorySpanExporter` (ships with otel-sdk) | Real export path, no server, green suite |
| Forcing a fallback in tests (stub lane) | Monkeypatching Router internals | `Router.completion(..., mock_testing_fallbacks=True)` | Verified hook at router.py:5624; raises `InternalServerError` → triggers fallback |
| Langfuse trace correlation | Manual span linking | langfuse v4 OTel-native `propagate_attributes` / `get_current_trace_id` | v4 is built on OTel; one tracer provider feeds both |

**Key insight:** litellm + langfuse-v4 + otel-sdk between them already implement every hard
part (routing, cost, transport, test hooks). The phase is *wiring + persistence + one binding
shim*, not building infrastructure.

## Runtime State Inventory

> N/A — Phase 3 is additive (new code paths + repository methods + dep pins). It does not
> rename, migrate, or rebrand existing stored state. The `budget_ledger`/`gateway_events`
> tables and `BudgetEvent`/`GatewayEvent` models already exist; no data migration, only new
> writers/readers. **None found in any rename/refactor category — verified by inspection of
> migrations/0001_init.sql and contracts/models.py.**

---

## Findings (the 6 research foci)

### Finding 1 — In-process `litellm.Router` construction + ChatLiteLLM binding (Focus #1, GW-01/GW-02)

**Confidence: HIGH** `[VERIFIED: .venv introspection]`

**Router construction from the yaml.** `litellm.Router.__init__` accepts (verified params)
`model_list`, `fallbacks`, `num_retries`, `timeout`, `context_window_fallbacks`,
`content_policy_fallbacks`, `routing_strategy`, plus many more. The
`config/model_gateway.config.yaml` maps directly:

```python
# model_gateway.py — loader
import yaml
from litellm import Router

def build_router(config_path="config/model_gateway.config.yaml") -> Router:
    cfg = yaml.safe_load(open(config_path))
    rs = cfg.get("router_settings", {})
    return Router(
        model_list=cfg["model_list"],          # litellm resolves os.environ/... at call time
        fallbacks=rs.get("fallbacks"),         # [{"low-complexity": ["medium-complexity"]}, ...]
        num_retries=rs.get("num_retries", 2),
        timeout=rs.get("timeout", 120),
    )
```
`litellm.Router.completion` is present with signature
`completion(self, model: str, messages: List[Dict], **kwargs) -> ModelResponse` — **identical**
to `litellm.completion`'s call shape. `acompletion` is also present. Cascades + retries execute
**in-process** inside `Router.completion` (confirms D-09).

**The binding gotcha (load-bearing).** `langchain_litellm.ChatLiteLLM` defaults its `client`
field to `None` (litellm.py:398), but a pydantic validator at **litellm.py:558**
**unconditionally** runs `values["client"] = litellm`, overwriting any user-supplied client.
So `ChatLiteLLM(client=router)` is silently ignored. Both `completion_with_retry` (line ~500)
and `acompletion_with_retry` call `self.client.completion(**kwargs)` / `await
self.client.acompletion(**kwargs)`.

**Recommended fix — thin subclass (option b):**
```python
# model_gateway.py
from langchain_litellm import ChatLiteLLM

class RouterChatLiteLLM(ChatLiteLLM):
    """ChatLiteLLM whose execution path is an in-process litellm.Router (D-09).

    The base class' validator clobbers `client` with the litellm module, so we
    bypass it by routing completion_with_retry / acompletion_with_retry through a
    held Router. Router.completion is signature-compatible with litellm.completion.
    """
    _router: object = None  # set post-init; Router routes by its own model_list

    def completion_with_retry(self, run_manager=None, **kwargs):
        return self._router.completion(**kwargs)

    async def acompletion_with_retry(self, run_manager=None, **kwargs):
        return await self._router.acompletion(**kwargs)
```
Then `get_chat_model()` constructs it and attaches the (process-cached) Router. Use a
`model=` that names a Router **deployment** (`model_name` from the yaml, e.g.
`"high-complexity"`), since the Router routes by deployment name, not raw provider model id.

> **D-06 interaction:** with the Router holding `api_base` per-deployment in `model_list`,
> the `api_base` on the chat model is no longer the chokepoint — see Finding 6.

**Alternatives if the subclass is rejected:** (a) `chat = ChatLiteLLM(...); chat.client =
router` post-construction — works but `_client_params` mutates `client.api_base/api_key/
extra_headers` each call (litellm.py:470-495); on a Router those attribute-sets are inert
(Router routes by `model_list`) but undocumented. The subclass is safer. Either way, **confirm
in planning with a trivial `.invoke` against a stubbed Router deployment** before building on it.

---

### Finding 2 — Pre-call cost estimation + clean budget halt (Focus #2, GW-01/GW-03)

**Confidence: HIGH** `[VERIFIED: .venv introspection]` — `litellm.completion_cost`,
`litellm.token_counter`, `litellm.cost_per_token`, `litellm.get_max_tokens` all present.

**The enforcement model (D-04/D-09):** the durable `budget_ledger` is the **sole** enforcer
in the in-process runtime. `general_settings.max_budget:50` is **inert** (asserted by config
only — Finding 6). The worker run loop wraps each model call:

```python
# pre-call (deterministic estimate — upper bound so a near-cap run halts BEFORE spend)
from litellm import token_counter, cost_per_token, get_max_tokens
prompt_tokens = token_counter(model=route.model, messages=messages)
max_out = settings.model_max_tokens  # 4096 cap
in_cost, out_cost = cost_per_token(model=route.model,
                                   prompt_tokens=prompt_tokens,
                                   completion_tokens=max_out)
est = in_cost + out_cost
budget.check(budget_owner, est)        # reads MTD from ledger; raises BudgetExceeded → clean halt
                                       # on raise: record a gateway_event (provider_status=None, note=budget_halt)

# the model call (Finding 1) ...

# post-call (actual)
usage = response.usage  # prompt_tokens, completion_tokens
actual = litellm.completion_cost(completion_response=response)
budget.record(BudgetEvent(budget_owner=..., task_id=..., model=route.model,
                          prompt_tokens=usage.prompt_tokens,
                          completion_tokens=usage.completion_tokens,
                          estimated_cost_usd=actual, tenant_id=..., client_slug=...))
```

**D-05 per-task attribution:** every `BudgetEvent`/`budget_ledger` row already carries
`task_id` (verified in the model + the table). Add an optional `per_task_cap` setting
defaulting to the per-user cap; `check()` enforces `min(per_user_remaining, per_task_remaining)`.

**Clean-halt proof for GW-03 (live lane):** set the per-user cap to a few cents
(`MODEL_MONTHLY_BUDGET_USD=0.02`). The first real call's pre-call estimate exceeds it →
`BudgetExceeded` → run transitions to a terminal halted state + a `gateway_event` is recorded
→ the assertion checks the ledger shows the halt and **no** provider call beyond the cap. This
is a real halt against real pricing, satisfying D-01/D-03 without faking the boundary.

**Estimation method recommendation:** pre-call = `cost_per_token(prompt_tokens=counted,
completion_tokens=max_tokens)` (conservative upper bound — never under-estimates, so the cap
is never breached by a single call). Post-call = `completion_cost(completion_response=...)`
(authoritative). The ledger stores the **actual** post-call cost; the pre-call estimate is
used only for the halt decision.

---

### Finding 3 — OTel → Langfuse v4 OTLP wiring + multi-exporter fan-out (Focus #3, OBS-01)

**Confidence: HIGH** `[VERIFIED: .venv introspection]`

**Langfuse v4 is OTel-native.** `Langfuse.__init__` accepts (verified) `tracer_provider`
**and** `span_exporter` directly, plus `public_key`, `secret_key`, `host`, `base_url`,
`environment`, `release`, `should_export_span`, `additional_headers`. This means the OTel
TracerProvider is the single source of spans; Langfuse is one consumer of it.

**Two telemetry paths must root under one trace (coherence #5):**
1. The graph run gets `langfuse.langchain.CallbackHandler` (v4 path) attached via
   `config={"callbacks":[handler]}` — covers planner/researcher/etc. node spans.
2. `litellm.Router` honors `litellm_settings.success_callback=["langfuse","otel"]` from the
   yaml — covers model-call spans.
   Under v4-OTel-native both feed the same `TracerProvider`, so they nest correctly **iff**
   they share the trace root. Root = the per-task `trace_id` set on `OrchestrationResult`
   (D-07). Use `langfuse.create_trace_id()` / `propagate_attributes(...)` to bind.

**Recommended OTel setup (configurable endpoint + in-memory CI seam):**
```python
# observability.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource

def init_tracing(settings, *, test_exporter=None):
    provider = TracerProvider(resource=Resource.create({
        "service.name": "agent-mesh-worker",
        "deployment.environment": settings.tenant_id,
    }))
    if test_exporter is not None:                      # CI: InMemorySpanExporter
        provider.add_span_processor(BatchSpanProcessor(test_exporter))
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        # Langfuse OTLP ingest endpoint + basic-auth header (public:secret base64)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,   # e.g. {LANGFUSE_HOST}/api/public/otel/v1/traces
            headers={"Authorization": "Basic <b64(public:secret)>"},
        )))
        # parallel-SIEM seam (D-07): add a SECOND processor/exporter here, Langfuse stays.
    trace.set_tracer_provider(provider)
    return provider
```

**Shared metadata as span attributes:** `trace_metadata()` already builds the dict
(`tenant_id, client_slug, task_id, session_id, requester_id, entrypoint, agent_role,
model_route_profile, approval_state`). Set each as a span attribute on the root span (OBS-01's
"correlate via shared request metadata").

**CI proof (D-07):** `InMemorySpanExporter` ships with `opentelemetry-sdk` (verified import).
Tests call `init_tracing(test_exporter=mem)`, run a stub mesh task, then
`mem.get_finished_spans()` and assert span names + the shared-metadata attributes — no server,
deterministic, green suite.

**Langfuse OTLP ingest endpoint (CITED):** Langfuse self-host / cloud exposes an OTLP/HTTP
trace receiver at `{host}/api/public/otel/v1/traces` with Basic auth (`public_key:secret_key`).
Confirm the exact path against the deployed Langfuse version in the live lane.
`[CITED: langfuse.com/docs OpenTelemetry integration]` `[ASSUMED for exact path — verify in live lane]`

**Cross-process correlation (coherence #6, OBS-01 requirement):** approval spans fire on the
ingress/API side; model/tool spans fire in the worker, with **Pub/Sub async dispatch between
them (DUR-03)**. OTel ambient context does NOT cross that boundary. To place approval events
under the task's `trace_id`, **propagate the W3C `traceparent` through the task record**: store
it when the task is created (ingress), restore it in the worker before starting the root span.
This is a concrete OBS-01 implementation task — "correlate" implies it but it is not free.

---

### Finding 4 — GW-03 cross-provider cascade trigger (Focus #4, GW-03)

**Confidence: HIGH** `[VERIFIED: .venv introspection]` — `mock_testing_fallbacks` handled at
`litellm/router.py:5624` (`_handle_mock_testing_fallbacks`), raises `InternalServerError` when
`mock_testing_fallbacks=True`; `mock_response` present in `litellm/main.py`.

**litellm fallback semantics:** the general `fallbacks` list fires on retryable provider
errors (5xx / rate-limit / timeout / `InternalServerError`). It is distinct from
`context_window_fallbacks` (context-length errors) and `content_policy_fallbacks` (moderation
errors); auth/4xx errors hard-fail rather than cascade. The yaml uses the **general**
`fallbacks` list, so the test must induce a *retryable* error class.

**Two-lane split (satisfies BOTH D-01 and D-02):**

- **Deterministic stub lane (`make test`, no creds, green CI):**
  ```python
  router.completion(model="low-complexity", messages=msgs, mock_testing_fallbacks=True)
  # raises InternalServerError on the primary deployment → Router cascades to the
  # configured fallback ("medium-complexity") → returns. Assert the fallback deployment served.
  ```
  This proves the *wiring* (fallback list is loaded and honored) without any provider call.

- **Live lane (`make test-live`, real providers, D-01/D-03):** induce a **real but
  deterministic** Vertex failure so a genuine error propagates and the **real Anthropic**
  fallback serves. Deterministic real-failure options (pick one in planning):
  - point the Vertex deployment at a **nonexistent model id** or **invalid `vertex_location`**
    → real Vertex API error → Anthropic fallback.
  - use an **invalid/empty `vertex_project`** → real auth/not-found error.
  A real provider error is **NOT a faked boundary** (D-01 satisfied): the Router really called
  Vertex, Vertex really failed, Anthropic really served. Configure the live-lane fallback so
  Vertex-primary → Anthropic-fallback specifically (per D-03), e.g. a dedicated test route
  `{"vertex-broken": ["high-complexity"]}`.

**Budget-halt half of GW-03:** covered by Finding 2's cents-cap clean halt. GW-03's full
acceptance ("model fallback AND budget-limit halt behave correctly") = stub-lane fallback +
live-lane real fallback + cents-cap halt, all asserted via the ledger/Router result.

---

### Finding 5 — `budget_ledger` + `gateway_events` schema (Focus #5, GW-01/GW-02)

**Confidence: HIGH** `[VERIFIED: migrations/0001_init.sql + contracts/models.py]`

**RESOLVED — no new migration needed.** Both tables **already exist** in
`migrations/0001_init.sql`:
- `budget_ledger` (lines 201-214): `budget_event_id, tenant_id, client_slug, budget_owner,
  task_id, model, prompt_tokens, completion_tokens, estimated_cost_usd NUMERIC(12,6),
  created_at`, with `idx_budget_owner_month ON (tenant_id, budget_owner, created_at)` —
  **this index already supports the month-to-date tenant-scoped SUM** the halt needs.
- `gateway_events` (lines 216-229): `gateway_event_id, tenant_id, client_slug, task_id,
  cf_aig_request_id, litellm_request_id, provider, model_route, provider_status, dlp_action,
  created_at`, with `idx_gateway_task ON (task_id)`.

Matching Pydantic models already exist: `BudgetEvent` (models.py:219) and `GatewayEvent`
(models.py:235), both tenant-scoped.

**The actual gap (repository methods).** The `Repository` protocol (repository.py:29-53) has
**zero** budget/gateway methods today. Work required:
1. Extend the `Repository` protocol with (tenant-scoped, per DUR-02):
   - `record_budget_event(event: BudgetEvent) -> BudgetEvent`
   - `budget_month_to_date(tenant_id: str, budget_owner: str, since: datetime) -> float`
     (SUM `estimated_cost_usd` — uses `idx_budget_owner_month`)
   - `record_gateway_event(event: GatewayEvent) -> GatewayEvent`
   - `list_gateway_events(task_id: str, tenant_id: str) -> list[GatewayEvent]`
2. Implement in `RepositorySQL` (psycopg3, `Jsonb` where needed, tenant-scoped WHERE).
3. Implement in `InMemoryRepository` (mirror method-for-method — the established pattern;
   keeps `make test` green without Postgres).
4. Rewire `budget.py` `BudgetTracker` to read MTD from `budget_month_to_date()` and write via
   `record_budget_event()` instead of the in-memory `_spent` dict — **keep the
   `check()`/`record()`/`month_to_date()` API shape** (D-04: "the API shape D-04 keeps").

**Per-task cap (D-05):** no schema change — `per_task_cap` is a settings value; per-task MTD is
a `budget_month_to_date` variant filtered by `task_id` (or compute from `list` rows).

---

### Finding 6 — D-06 chokepoint relocation + config assertion (GW-02, coherence #3)

**Confidence: HIGH** `[VERIFIED: config + .venv]`

With the in-process Router (D-09), the `api_base` that matters is **per-deployment** inside the
Router's `model_list` — each `litellm_params.api_base = os.environ/CF_AIG_WRAPPER_URL` (already
in `config/model_gateway.config.yaml`, every route). It is **not** on the chat model anymore.
So the D-06 guard must be **relocated**:

- **Config assertion test:** load the yaml, iterate `model_list`, assert every
  `litellm_params.api_base` resolves to the CF wrapper URL when `CF_ENABLED` is true.
- **Structural guard test:** treat the **Router** as "the client." Assert `get_chat_model()`
  returns a `RouterChatLiteLLM` whose Router was built from the yaml (so every route inherits
  the CF `api_base`); fail if any code path constructs a provider client (`ChatAnthropic`,
  `ChatVertexAI`, raw `litellm.completion`) directly without going through `get_chat_model()`.
  A simple AST/grep guard test over `src/` for forbidden direct-provider imports is the
  cheapest enforcement.
- **`CF_ENABLED` flag:** when off, routes go direct to providers (valid POC state per D-06);
  when on, `api_base` = CF wrapper. Add `cf_enabled` + `cf_aig_wrapper_url` to `settings.py`.

`general_settings.max_budget:50` and `master_key` stay in the yaml as **prod-proxy config
asserted structurally** (D-09): a config test asserts they are present/well-formed, but they
are never executed in-process.

---

### Finding 7 — Langfuse v4 prompt/version + datasets/evals (Focus #6 partial, OBS-02/D-08)

**Confidence: HIGH** `[VERIFIED: .venv introspection]` — langfuse v4 client surface:
- prompts: `create_prompt`, `get_prompt`, `update_prompt`, `clear_prompt_cache`
- datasets: `create_dataset`, `create_dataset_item`, `get_dataset`, `get_dataset_run`,
  `get_dataset_runs`, `delete_dataset_run`
- evals/scores: `create_score`, `run_batched_evaluation`, `score_current_span`,
  `score_current_trace`
- trace ids: `create_trace_id`, `get_current_trace_id`, `get_trace_url`

**D-08 (thin/seeded) maps cleanly:**
- **Prompt/version mgmt with fetch-with-fallback:**
  ```python
  def get_prompt_with_fallback(name, local_default):
      try:
          return get_client().get_prompt(name).prompt   # pulls versioned prompt from Langfuse
      except Exception:
          return local_default                            # keeps make test green offline
  ```
  Register ≥1 versioned prompt via `create_prompt(name=..., prompt=..., labels=["production"])`
  (a one-shot seed script / `make seed-langfuse`, live-lane only).
- **Seed one dataset:** `create_dataset(name="phase3-seed")` +
  `create_dataset_item(dataset_name=..., input=..., expected_output=...)` from task evidence.
- **Example/trivial eval:** register a trivial scorer via `create_score(...)` on a dataset run
  to prove the path. **The real scoring engine is Phase 4 / SI-01 — do not pull it forward.**

> OBS-02 is **Langfuse-native**; OTel does not cover prompt/version/datasets/evals (D-07
> split). These calls require Langfuse creds and are therefore **live-lane only**; the default
> suite uses the local fallback.

---

## Common Pitfalls

### Pitfall 1: `ChatLiteLLM(client=router)` silently ignored
**What goes wrong:** the Router never executes; calls go through the bare `litellm` module,
bypassing routing/cascade/budget — and there is no error.
**Why:** validator at `langchain_litellm/.../litellm.py:558` runs `values["client"] = litellm`
unconditionally.
**How to avoid:** use the `RouterChatLiteLLM` subclass (Finding 1). Verify with a trivial
`.invoke` against a stubbed Router deployment in planning before building.
**Warning sign:** model spans show no Router deployment name; fallback test "passes" without a
Router in the path.

### Pitfall 2: Langfuse v2 import path (dead under v4)
**What goes wrong:** `from langfuse.callback import CallbackHandler` →
`ModuleNotFoundError: No module named 'langfuse.callback'` (verified). `observability.py`
currently uses this — it is **broken against the installed 4.7.1**.
**How to avoid:** `from langfuse.langchain import CallbackHandler`. Bump `pyproject` to
`langfuse>=4,<5`.
**Warning sign:** observability silently returns `None` (the except-swallow at
observability.py:83) → no traces, no error.

### Pitfall 3: D-06 guard test asserts a now-meaningless field
**What goes wrong:** a test asserting `ChatLiteLLM.api_base == CF_URL` passes but proves
nothing — under the Router, that field is not the egress path.
**How to avoid:** relocate the guard to the Router `model_list` per-route `api_base` + a
direct-provider-import grep guard (Finding 6).

### Pitfall 4: OTel context lost across Pub/Sub
**What goes wrong:** approval spans (ingress) and model spans (worker) land in **separate
traces** → OBS-01 "correlate" fails.
**How to avoid:** store W3C `traceparent` in the task record at ingress; restore in the worker
(Finding 3 / coherence #6).

### Pitfall 5: Python 3.14 + pydantic-v1 warnings
**What goes wrong:** the venv runs **Python 3.14**; both `langfuse.api` and `langchain_core`
emit `UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14 or
greater`. If these escalate to errors (or a `filterwarnings = error` pytest config), they break
the "green suite, no cloud deps" invariant.
**How to avoid:** confirm pytest does not treat warnings as errors; consider pinning a tested
Python (pyproject says `>=3.11`). Flag to user — this is environment drift, not a Phase-3
deliverable, but it can block CI.
**Warning sign:** import-time `UserWarning` in test output (already visible in this research).

### Pitfall 6: Trusting `max_budget:50` to enforce
**What goes wrong:** planner assumes LiteLLM hard-stops at $50; it does not in the in-process
runtime (the proxy `general_settings` is not executed).
**How to avoid:** the durable ledger pre-call `check()` is the sole enforcer (D-04/Finding 2).

## State of the Art

| Old Approach (training / pyproject pin) | Current (verified installed) | Impact |
|------------------------------------------|------------------------------|--------|
| `langfuse>=2.0`, `langfuse.callback.CallbackHandler` | langfuse **4.7.1**, `langfuse.langchain.CallbackHandler`, **OTel-native** | v2 import is DEAD; v4 being OTel-native is *better* for D-07 (one tracer provider, native fan-out). MUST migrate `observability.py` + pin. |
| LiteLLM proxy server as the gateway | In-process `litellm.Router` (D-09) | No standalone proxy SPOF; routing/cascade/budget in testable Python. |
| OTel deps absent from pyproject | otel-api/sdk 1.42.1 present (transitive); HTTP OTLP exporter available, gRPC NOT | Pin the **HTTP** OTLP exporter only. |

**Deprecated/outdated for this phase:**
- `from langfuse.callback import CallbackHandler` — removed in v3+.
- Any plan that adds a new migration for budget/gateway tables — they already exist.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Langfuse OTLP ingest path is `{host}/api/public/otel/v1/traces` with Basic(public:secret) auth | Finding 3 | LOW — live-lane only; verify against the deployed Langfuse version; default suite uses in-memory exporter so CI is unaffected |
| A2 | A nonexistent Vertex model id / invalid location produces a *retryable* error class that triggers the general `fallbacks` list (not a hard 4xx that skips fallback) | Finding 4 | MEDIUM — if it hard-fails, switch the live-lane trigger to a 5xx-class inducer or use `context_window_fallbacks`; confirm in the live lane during planning |
| A3 | The `RouterChatLiteLLM` subclass override survives `.invoke` (LangChain's `_generate` calls `completion_with_retry`) | Finding 1 | MEDIUM — verify with a trivial stubbed `.invoke` before building; fallback is post-hoc `chat.client = router` |
| A4 | Python 3.14 pydantic-v1 warnings stay warnings (not errors) under the project's pytest config | Pitfall 5 | MEDIUM — if pytest escalates warnings, the green-suite invariant breaks; check `filterwarnings` and consider Python pin |
| A5 | `langchain-litellm` 0.6.4 `completion_with_retry`/`acompletion_with_retry` method names are stable across the `>=0.6` floor | Finding 1 | LOW — verified in installed source; bump floor to `>=0.6` to lock the shape |

## Open Questions (RESOLVED)

> All three are live-lane RUNTIME decisions surfaced as settings/flags, not structural
> guesses — each is resolved in the Phase 3 plan actions as noted inline below.

1. **Exact Langfuse OTLP endpoint path for the deployed instance.** **(RESOLVED — A1)**
   Resolved by making the endpoint a SETTING (`settings.otel_exporter_otlp_endpoint`, added in
   03-01 Task 1; consumed by 03-03 Task 1 `init_tracing`). The exact `{host}/api/public/otel/v1/traces`
   path is a live-lane value verified opt-in, never hardcoded as a structural assumption.
   - Know: v4 ingests OTLP/HTTP; default suite uses in-memory exporter.
   - Unclear (live-lane only): exact path/version of the live Langfuse the user runs.
2. **Which deterministic real-Vertex-failure inducer the user prefers for GW-03 live lane**
   (bad model id vs bad location vs empty project). **(RESOLVED — A2)**
   Resolved in 03-02: the live-lane cascade test induces a real deterministic Vertex failure (planner
   picks the inducer) → real Anthropic fallback serves; confirmed to trigger the general fallback in
   the live lane. The stub lane uses `mock_testing_fallbacks=True` (no creds).
3. **Python version pin.** venv is 3.14 with pydantic-v1 warnings. **(RESOLVED — A4)**
   Resolved in 03-01 Task 1: surfaced as a runtime decision — `filterwarnings` is verified NOT to
   escalate the Py-3.14 pydantic-v1 UserWarning to error (ignore entry added if needed), preserving the
   green-suite invariant. Whether to pin a different Python is left to the operator; the suite stays
   green on 3.14 as-is.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| litellm | GW-01/GW-03 Router | ✓ (.venv) | 1.83.7 | — |
| langchain-litellm | get_chat_model binding | ✓ | 0.6.4 | — |
| langfuse | OBS-01/OBS-02 | ✓ | 4.7.1 | local fetch-with-fallback (D-08) keeps suite green |
| opentelemetry-api/sdk | OBS-01 transport | ✓ | 1.42.1 | InMemorySpanExporter (no server) |
| OTLP HTTP exporter | live OTLP export | ✓ (importable) | 1.42 | in-memory exporter (CI) |
| OTLP gRPC exporter | (not used) | ✗ | — | HTTP exporter (use this) |
| Postgres (DATABASE_URL) | durable budget_ledger | ✗ (local) | — | InMemoryRepository mirror (make test) |
| Anthropic API key | live lane | ✗ (CI) | — | stub lane / `pytest -m live` opt-in (D-02) |
| Vertex/GCP creds (ADC/SA) | live lane | ✗ (CI) | — | stub lane / `pytest -m live` opt-in (D-02) |
| Docker | (Phase 2 sandbox; not Phase 3) | n/a | — | — |

**Missing with no fallback:** none for the default suite (everything degrades to stub/in-memory).
**Missing with fallback:** provider creds + Postgres — both are opt-in/live-lane by design (D-02).

## Validation Architecture

> `workflow.nyquist_validation` not found as `false` in config → section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 (dev extra) `[VERIFIED: pyproject]` |
| Config file | `[tool.pytest.ini_options]` in `pyproject.toml` (`pythonpath=["src"]`, `testpaths=["tests"]`) |
| Quick run command | `pytest tests/ -x -q` (stub lane; no creds) |
| Full suite command | `make test` (deterministic) / `make test-live` (opt-in, `pytest -m live`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GW-01 | Router built from yaml; routes resolve; budget halt via ledger | unit | `pytest tests/test_model_gateway.py -x` | ❌ Wave 0 |
| GW-01 | Pre-call estimate + post-call record write budget_ledger (tenant-scoped) | unit | `pytest tests/test_budget_ledger.py -x` | ❌ Wave 0 |
| GW-02 | Every route `api_base` == CF wrapper when CF_ENABLED; no direct-provider import | unit/guard | `pytest tests/test_d06_chokepoint.py -x` | ❌ Wave 0 |
| GW-03 | Stub-lane fallback via `mock_testing_fallbacks` | unit | `pytest tests/test_cascade.py -x` | ❌ Wave 0 |
| GW-03 | Live Vertex→Anthropic fallback + cents-cap clean halt | live | `pytest tests/test_cascade_live.py -m live` | ❌ Wave 0 |
| OBS-01 | InMemorySpanExporter asserts spans + shared-metadata attrs; trace_id set on result | unit | `pytest tests/test_observability_otel.py -x` | ❌ Wave 0 |
| OBS-01 | traceparent propagates across task record (ingress→worker) | unit | `pytest tests/test_trace_propagation.py -x` | ❌ Wave 0 |
| OBS-02 | get_prompt fetch-with-fallback returns local default offline | unit | `pytest tests/test_langfuse_prompts.py -x` | ❌ Wave 0 |
| OBS-02 | seed prompt/dataset/eval against real Langfuse | live | `pytest tests/test_langfuse_seed_live.py -m live` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -q` (stub lane)
- **Per wave merge:** `make test` (full deterministic suite)
- **Phase gate:** full deterministic suite green + live lane run once with user creds before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/conftest.py` — add a `live` marker registration + an `InMemorySpanExporter` fixture + a stubbed-Router fixture
- [ ] Register `pytest -m live` marker in `[tool.pytest.ini_options].markers`
- [ ] `make test-live` target in Makefile (drives `pytest -m live`)
- [ ] Dep install: `langfuse>=4,<5`, `opentelemetry-api/sdk>=1.42`, `opentelemetry-exporter-otlp-proto-http>=1.42`, `langchain-litellm>=0.6`

## Security Domain

> `security_enforcement` not disabled in config → section included.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (secondary) | Provider keys + Langfuse keys + CF shared-secret resolved from env/Secret Manager at runtime, never in code/prompts (CLAUDE.md §5) |
| V4 Access Control | yes | Tenant scoping on every budget/gateway read (DUR-02); approval ledger remains the sole write-decision authority — observability OBSERVES approval events, never gates (D-07) |
| V5 Input Validation | partial | BudgetEvent/GatewayEvent are Pydantic-validated models |
| V6 Cryptography | yes (preserve) | Do NOT weaken SEC-01/SEC-02 when adding approval spans: signed token, payload-hash binding, replay guard stay intact; the OTel span is read-only telemetry |
| V7 Errors & Logging | yes (core) | OTel spans + gateway_events are the audit trail; 12-mo retention (NFR); do not log provider keys or full prompt bodies into spans where DLP applies (CF owns body governance) |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Approval span carries/leaks approver identity as a trust signal | Elevation of Privilege | Span is telemetry only; approver derived solely from signed token (SEC-01); never branch on span data (mirrors graph.py RF-1 invariant) |
| Cross-tenant budget read (one tenant sees another's MTD) | Information Disclosure | tenant-scoped WHERE on `budget_month_to_date` / `list_gateway_events` (DUR-02) |
| Secret leakage into spans / Langfuse | Information Disclosure | Never set api_key/raw creds as span attributes; CF AI Gateway owns DLP on bodies; keep keys in env |
| Budget bypass via direct provider call | Tampering / cost abuse | D-06 structural guard: no direct-provider client construction outside get_chat_model() |
| Replay of a budget halt / forged gateway_event | Tampering | gateway_events are append-only durable rows; halt is a run-control decision, not an approval |

## Sources

### Primary (HIGH confidence — verified in project `.venv`)
- `./.venv/bin/python` introspection of: litellm 1.83.7 (`Router.__init__`, `Router.completion`,
  `completion_cost`/`token_counter`/`cost_per_token`/`get_max_tokens`, `mock_testing_fallbacks`
  at router.py:5624), langchain-litellm 0.6.4 (`ChatLiteLLM` fields, validator clobber at
  litellm.py:558, `_client_params` at 465-495, `completion_with_retry`/`acompletion_with_retry`),
  langfuse 4.7.1 (`Langfuse.__init__` `tracer_provider`/`span_exporter`, `langfuse.langchain`
  handler, prompt/dataset/eval client surface, dead `langfuse.callback`), opentelemetry-sdk
  1.42.1 (`InMemorySpanExporter`, HTTP OTLP present / gRPC absent).
- In-repo: `migrations/0001_init.sql` (budget_ledger + gateway_events tables already present),
  `contracts/models.py` (BudgetEvent/GatewayEvent models), `worker/model_gateway.py`,
  `worker/budget.py`, `observability.py`, `worker/graph.py`, `worker/orchestrator.py`,
  `settings.py`, `services/repository.py`, `config/model_gateway.config.yaml`, `pyproject.toml`.
- `CLAUDE.md` §1–§3, §5, §6 (#5/#6/#7/#16), §8; `.planning/` CONTEXT/REQUIREMENTS/ROADMAP/STATE.

### Secondary (MEDIUM)
- Langfuse docs OpenTelemetry integration (OTLP ingest endpoint shape) — `[CITED]`, exact path
  to be confirmed against the deployed version (A1).

### Tertiary (LOW)
- None relied upon for load-bearing claims.

## Project Constraints (from CLAUDE.md)
- LangChain + LangGraph + Deep Agents + **Langfuse REQUIRED**; **LangSmith never a dependency**
  (no LangSmith import anywhere in this phase).
- Model-gateway separation: LiteLLM = control plane (routing/budgets/cascades/provider
  abstraction); CF AI Gateway = model-traffic governance (logging/DLP/blocking/guardrails);
  flow LangChain → LiteLLM (in-process Router) → CF edge → providers; agents never call
  providers directly.
- §6 #5 gateway-routed/never-direct (D-06 guard); #6 CF integration-ready, does NOT replace
  tool-write gates; #7 $50 per-user/per-task budget; #16 Langfuse-centered observability.
- §8 guardrails: write-approval gate holds (payload-hash bound); no runtime autonomous
  self-modification; bounded declared roster; durable ledger is the sole budget enforcer in the
  in-process runtime.
- Deploy-ready only — NO live GCP provisioning this milestone; `make test`/`make smoke` green
  with no cloud deps (live lane is opt-in).

## Metadata

**Confidence breakdown:**
- Standard stack / versions: **HIGH** — every version read from the installed `.venv`.
- In-process Router binding (Finding 1): **HIGH** — validator clobber + method shapes verified
  in source; one runtime `.invoke` check recommended (A3).
- Budget estimation (Finding 2): **HIGH** — cost helpers verified present.
- OTel/Langfuse wiring (Finding 3): **HIGH** for SDK surface; **MEDIUM** for exact OTLP path (A1).
- GW-03 trigger (Finding 4): **HIGH** for stub-lane hook; **MEDIUM** for live-lane error class (A2).
- Schema (Finding 5): **HIGH** — tables + models verified already present.
- D-06 relocation (Finding 6): **HIGH**.
- OBS-02 surface (Finding 7): **HIGH** — client methods enumerated from installed v4.

**Research date:** 2026-06-06
**Valid until:** 2026-07-06 (stack is fast-moving — litellm/langfuse ship frequently; re-verify
versions if planning slips past ~30 days)

## RESEARCH COMPLETE
