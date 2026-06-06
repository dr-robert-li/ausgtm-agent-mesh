# Phase 4: Tool Gateway Framework + First Adapters + Aggregators - Research

**Researched:** 2026-06-06
**Domain:** SaaS tool-execution engine (credential resolution + JSON-Schema boundary + OTel spans) and two integration styles (direct adapters + MCP/unified-API aggregators) over a LangGraph worker.
**Confidence:** HIGH on code seams + jsonschema + Composio/HubSpot/Google; MEDIUM-HIGH on Nango (corrected a package assumption); MEDIUM on exact per-product GWS operation set (Claude's discretion, planner decides).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01..D-12 — verbatim)
- **D-01:** POC = MVP, full tool coverage in v1. Reusable tool spine + the two flagship direct providers + both aggregator styles — not a one-adapter proof. Every provider independently landable and testable; the long tail (Phase 5) must be thin-adapter-plus-config on top of this engine, never a rearchitecture.
- **D-02:** Credential resolution at execution time, Secret-Manager-shaped, env-backed locally. A `CredentialResolver` resolves by the manifest's `credential_secret_name` at `execute()` time; prod swaps to real Secret Manager. Agents never receive raw credentials. The deterministic stub lane resolves nothing (stays creds-free).
- **D-03:** Loader carries what it currently drops. `ToolSpec` / `load_tool_pack` must surface `integration_style` and `input_schema_ref` / `output_schema_ref`. The write-class invariant (`category ∈ WRITE_CATEGORIES ⇒ approval_required`) stays.
- **D-04:** Validate against a schema, source depends on integration style. Direct adapters validate against OUR manifest-declared schemas. Aggregate tools validate against the aggregator/provider-supplied schema fetched at runtime. **Fail-closed applies to direct tools only:** a direct tool with no declared schema is blocked. Fail-closed NEVER applies to aggregate tools.
- **D-05:** Permissive-by-design authoring. Schemas validate required fields + types and allow additional properties by default; tighten (`additionalProperties:false`, enums, bounds) only on cost/security-critical fields. Gate width is an authoring choice, not a property of validation.
- **D-06:** Asymmetric input/output failure actions. Input violation → hard reject, no SaaS call made, record a failed `tool_call`. Output violation → flag/quarantine the result + record it and halt downstream trust; validate primarily the output fields the agent consumes. The deterministic reject test (success criterion #2, default lane) uses a tool that DOES declare schemas.
- **D-07:** HubSpot = read + approval-gated write, on a dev/test sandbox. `hubspot_lookup_company` (read, unconditional live call) AND `hubspot_create_deal` (write, approval-gated through the existing ledger). Single bearer private-app token. Live writes hit a HubSpot developer/test sandbox.
- **D-08:** Google Workspace = full suite live. Gmail, Calendar, Drive, Sheets, Docs, Slides as live direct adapters this phase (not a starter subset). Reads run unconditionally in the live lane; writes/sends are approval-gated. OAuth app + refresh-token; per-product scopes documented (D-12). Planner sets the per-product operation set. Scope flag (D-08 × D-04): every GWS tool needs a manifest entry AND input/output schemas; treat adapter+manifest+schema as one unit per product.
- **D-09:** Composio primary + Nango fallback; one real read each, end-to-end. Composio (managed auth, MCP-native single Tool Router endpoint — Spike 001 winner) and Nango (self-hosted OSS unified API) each make one real read call through the gateway. A read avoids approval-gate coupling and proves the integration style end-to-end. Heavy provider matrix and any write-through-aggregator are Phase 5. Nango requires a local/self-hosted instance for its live lane.
- **D-10:** Tool-event OTel spans land here. The engine emits an OTel span per tool call (`tool`, `provider`, `category`, `integration_style`, latency, `approval_state`, outcome) using `observability.trace_metadata()` over the Phase-3 OTel transport. Closes OBS-01 Gap-2.
- **D-11:** Per-provider opt-in live-lane matrix. Default `make test` / `make smoke` stay green and creds-free on the deterministic stub path. Real calls run only in a marked live lane, and each provider (and each aggregator) is independently skippable when its creds are absent.
- **D-12:** Per-provider credential/scope setup doc is a real Phase-4 deliverable. For each provider requiring creds, document how to mint the token/OAuth app and the exact scopes required (HubSpot private-app token + scopes; GWS OAuth client + per-product scopes; Composio managed-auth setup; Nango self-host + connection setup).

### Claude's Discretion (research + planning)
- Exact `CredentialResolver` interface + env-var naming convention; JSON-Schema validation library (`jsonschema`) and Draft version; where/how runtime aggregator schemas are fetched + cached.
- `ToolGateway.execute()` signature evolution and the failed-`tool_call` row shape.
- Per-product Google Workspace operation granularity (which read/write ops per product) within the "full suite live" boundary.
- Composio SDK-vs-MCP-endpoint binding into the gateway; depth of the Nango self-host setup for the live lane.
- OAuth refresh-flow mechanics for the GWS live lane (how the refresh token is supplied/rotated in test).

### Deferred Ideas (OUT OF SCOPE)
- Reference-adapter breadth → Phase 5 (TOOL-03): Webflow, Bitscale, Cal.com, Clockify, Beehiiv as direct adapters; Xero via aggregator (already `nango_aggregator` in the manifest). Plus the heavy aggregator provider matrix and any write-through-aggregator proof.
- Self-improvement → Phase 6 (SI-01/02): real eval harness; AI-BOM-on-promotion + controlled versioned (non-hot) promotion + rollback.
- Deeper Slack interaction surface (slash commands, richer approval UX) — ingress is already built; backlog only.
- v2 / production hardening: live GCP provisioning + FinOps (DEP-03/04); immutable ledger, egress controls, signed images, HA.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-01 | At least one real SaaS tool adapter (Google Workspace or HubSpot) executes a real call locally behind the Tool Gateway with credential resolution at execution time. | `CredentialResolver` pattern (env-backed, Secret-Manager-shaped); HubSpot (`hubspot-api-client` 12.0.0) + GWS (`google-api-python-client` 2.197.0, refresh-token `Credentials`) adapter examples + exact scopes; `execute(call)` signature change carrying tenant/task context; read-execution seam (item A) routes reads through `gateway.execute()`. |
| TOOL-02 | Tool input and output validated against JSON Schema at the tool boundary. | `jsonschema` 4.26.0 `Draft202012Validator` (matches on-disk schema `$schema`); D-04 fail-closed-direct-only dispatch; D-05 permissive authoring; D-06 asymmetric input-reject / output-quarantine mechanics + failed-`tool_call` row shape; runtime aggregate-schema fetch + cache. |
| TOOL-04 | Aggregate-MCP, Nango-aggregator, and Composio-aggregator integration styles exercised end-to-end; Composio primary + Nango fallback. | Composio SDK binding (`from composio import Composio`, `session.tools()`/`session.mcp.url`) + runtime schema fetch; Nango via REST proxy + `httpx` (NO official Python SDK — correction); self-host docker-compose; per-aggregator live lane (one real read each). |
| OBS-01 (tool-span leftover) | Tool-event OTel spans (deferred from Phase 3 — closed once a real adapter exists). | D-10 span emission via `observability.get_tracer()` + `set_span_metadata()` (Phase-3 transport, test-injectable); span attributes `tool/provider/category/integration_style/approval_state/outcome`; no-op when OTel absent. |
</phase_requirements>

## Summary

Phase 4 turns `tools/gateway.py` from an echo into a real execution engine. The codebase is unusually well-prepared for this: the manifest already declares `integration_style` + schema refs (the loader just drops them — D-03), the three direct schemas already exist on disk in **JSON Schema Draft 2020-12**, the approval ledger + payload-hash gate is generic and tool-agnostic, the OTel transport (`observability.get_tracer` + `set_span_metadata`) is built and only needs a tool span emitted, and the per-provider opt-in live lane (`@pytest.mark.live` + creds-present skip) is an established pattern. The work is **wiring real adapters into proven seams**, not new architecture.

The single plan-shaping item is the **read-execution seam (audit item A)**: there is no executed-read path today — `OrchestrationResult` carries only `proposed_writes` + `evidence`, and `runner.py` executes only writes after approval. HubSpot lookup, Drive search, and both aggregator reads are READS. The recommended approach (below) mirrors the existing `proposed_writes` mechanic with a `proposed_reads` list that the Worker executes **ungated, immediately, post-run**, recording `category=read` ToolCalls and feeding `evidence`. This reuses `runner._execute` / the `gateway is None → stub` fallback with zero changes to the approval gate and zero gateway injection into creds-gated graph nodes.

Two corrections to assumptions matter for the planner: **(1) The documented Nango SDK is `@nangohq/node`; no Python SDK was found** (single-source: the NangoHQ/nango repo README), and the PyPI `nango` 0.1.2 package is uncorroborated/suspect — so integrate via Nango's REST **proxy endpoint** (`GET/POST {NANGO_HOST}/proxy`) with the already-present `httpx`. The proxy recommendation is robust regardless of whether a Python SDK later appears. **(2) `execute()` must change signature** — D-10 spans, cred resolution, and the tool_call record all need task/tenant correlation, so `execute()` should take the `ToolCall` (or a small context object), not just `(name, parameters)`.

**Primary recommendation:** Build the engine as `ToolGateway.execute(call: ToolCall, *, resolver, tenant_id, ...) → dict` with three internal collaborators — `CredentialResolver` (env-backed, Secret-Manager-shaped), a `SchemaValidator` (Draft202012Validator, input pre-call / output post-call, asymmetric failure per D-06), and a per-`integration_style` adapter dispatch (`direct_api` → provider SDK; `composio_aggregator`/`aggregate_mcp` → `composio` SDK; `nango_aggregator` → `httpx` to Nango proxy). Emit one OTel tool span per call. Add a `proposed_reads` seam for ungated reads. Every adapter degrades to the existing deterministic stub when its creds are absent (D-11). Pin all provider deps as **optional extras** (`tools`, `aggregators`) so the default lane stays importable and creds-free.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Tool execution engine (dispatch, cred resolve, validate) | API/Backend (`tools/gateway.py`) | — | Single chokepoint; agents never hold creds (D-02) |
| Credential resolution | API/Backend (`CredentialResolver`) | Database/Secrets (Secret Manager in prod, env locally) | Resolves at `execute()` time only; never reaches the agent/graph |
| Schema validation boundary | API/Backend (`tools/`) | — | Direct = our schemas; aggregate = runtime provider schemas (D-04) |
| Read-tool execution | API/Backend (`worker/runner.py` Worker) | Orchestration (`graph.py` researcher node emits `proposed_reads`) | Ungated; runs post-mesh like writes run post-approval |
| Write-tool execution | API/Backend (`worker/runner.py`) | HITL (`services/approvals.py` ledger) | Unchanged P1/P2 path; payload-hash gated |
| Tool-event OTel span | Observability (`observability.py`) | API/Backend (emitted inside `execute()`) | Reuses Phase-3 transport; closes OBS-01 (D-10) |
| Aggregator brokering | External (Composio SaaS / self-hosted Nango) | API/Backend (adapter shim) | Composio managed-auth; Nango self-host REST proxy |

## Standard Stack

### Core (new this phase)
| Library | Version (PyPI 2026-06-06) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `jsonschema` | **4.26.0** | TOOL-02 input/output validation at the boundary | The canonical Python JSON-Schema validator; ships `Draft202012Validator` matching the existing schema files' `$schema`. `[VERIFIED: pip index versions + codebase $schema match]` |
| `hubspot-api-client` | **12.0.0** | HubSpot direct adapter (lookup + create deal) | HubSpot's official Python SDK. `[CITED: developers.hubspot.com]` package name; `[ASSUMED]` version pin until human-verify |
| `google-api-python-client` | **2.197.0** | Google Workspace direct adapters (Gmail/Calendar/Drive/Sheets/Docs/Slides) | Google's official discovery-based client; one client covers all six products. `[CITED: developers.google.com]` |
| `google-auth` | **2.53.0** | OAuth2 `Credentials` from a stored refresh token (unattended live lane) | Official auth library; `Credentials(refresh_token=...)` auto-refreshes. `[CITED: googleapis/google-api-python-client]` |
| `google-auth-oauthlib` | **1.4.0** | One-time refresh-token minting helper (`InstalledAppFlow`) for the setup doc only | Standard companion for the consent flow that mints the refresh token. `[ASSUMED]` |
| `composio` | **0.13.1** | Composio aggregator (primary) — managed auth + tool fetch + MCP Tool Router | `from composio import Composio` confirmed current. `[CITED: docs.composio.dev/getting-started/quickstart]` |
| (no new dep) `httpx` | already core | **Nango aggregator** via REST proxy — Nango has **no official Python SDK** | `httpx` is already a core dependency; the Nango proxy is plain HTTP. `[VERIFIED: github.com/NangoHQ/nango — SDK is `@nangohq/node` only]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `requests`/`httpx` raw REST | core `httpx` | HubSpot raw-REST fallback if the SDK proves heavy | Optional; SDK preferred for typed models |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `hubspot-api-client` SDK | raw `httpx` to `api.hubapi.com/crm/v3/...` | Raw REST is dependency-free but you hand-build object/search bodies; SDK gives typed helpers. Either is fine — D-07 only needs one bearer token. |
| `composio` SDK binding | Composio MCP endpoint via raw MCP client (`session.mcp.url`) | SDK (`session.tools()`) is simpler for one read; MCP endpoint is the "Tool Router" path. **Recommend SDK for Phase 4** (one real read); MCP-endpoint binding is a Phase-5 breadth concern. |
| PyPI `nango` package | Nango REST proxy via `httpx` | **`nango` 0.1.2 on PyPI is NOT the official client** — flag and avoid. REST proxy is the supported Python path. |
| `google-api-python-client` | per-product libs (`google-cloud-*`) | Workspace (Gmail/Calendar/Drive/Sheets/Docs/Slides) is NOT covered by `google-cloud-*`; the discovery client is the correct single-client choice. |

**Installation (proposed optional extras — keeps default lane creds-free + importable):**
```bash
# new groups in pyproject.toml [project.optional-dependencies]
tools = [
  "jsonschema>=4.18,<5",          # Draft202012Validator floor is 4.18
  "hubspot-api-client>=12,<13",
  "google-api-python-client>=2.190",
  "google-auth>=2.40",
  "google-auth-oauthlib>=1.2",
]
aggregators = [
  "composio>=0.13,<1",
  # Nango: NO python dep — uses core httpx against the Nango proxy REST API.
]
```
> `jsonschema` may instead go in the always-on `dependencies` list (it is small, pure-Python, no creds) so the schema boundary is never an optional import. **Recommend `jsonschema` as a core dep**, provider SDKs as extras. Planner decides.

## Package Legitimacy Audit

> **slopcheck was unavailable** (sandbox classifier denied the undeclared `pip install slopcheck`). Per the graceful-degradation rule, every package below is tagged `[ASSUMED]` and the planner **must gate each install behind a `checkpoint:human-verify` task** before adding to pyproject. Registry existence (verified via `pip index versions`) plus official-doc cross-reference is the substitute signal — it is NOT equivalent to a clean slopcheck pass.

| Package | Registry | Latest | Source / Official-doc cross-ref | slopcheck | Disposition |
|---------|----------|--------|---------------------------------|-----------|-------------|
| `jsonschema` | PyPI | 4.26.0 | python-jsonschema/jsonschema (ubiquitous) | unavailable | Approved `[ASSUMED]` — human-verify |
| `hubspot-api-client` | PyPI | 12.0.0 | developers.hubspot.com official SDK | unavailable | Approved `[ASSUMED]` — human-verify |
| `google-api-python-client` | PyPI | 2.197.0 | googleapis/google-api-python-client | unavailable | Approved `[ASSUMED]` — human-verify |
| `google-auth` | PyPI | 2.53.0 | googleapis/google-auth-library-python | unavailable | Approved `[ASSUMED]` — human-verify |
| `google-auth-oauthlib` | PyPI | 1.4.0 | googleapis companion lib | unavailable | Approved `[ASSUMED]` — human-verify |
| `composio` | PyPI | 0.13.1 | docs.composio.dev confirms `from composio import Composio` | unavailable | Approved `[ASSUMED]` — human-verify. **Note low major (0.x): API churns; pin tight.** |
| `nango` | PyPI | 0.1.2 | **NOT official** — Nango ships `@nangohq/node` only; no Python SDK | unavailable | **DO NOT INSTALL** — use `httpx` to the Nango REST proxy instead |

**Packages removed:** `nango` (PyPI) — not the official client; cross-ecosystem confusion risk (the real SDK is npm `@nangohq/node`). Nango integration uses core `httpx`.
**Packages flagged suspicious:** `composio` is a 0.x release with documented historical package-name churn (`composio-core` → `composio`); pin `>=0.13,<1` and human-verify the import path at install time.

*Every package above is `[ASSUMED]`; the planner inserts a `checkpoint:human-verify` before each pyproject edit / install.*

## Architecture Patterns

### System Architecture Diagram

```
                     LangGraph mesh (worker/graph.py)
   prompt ─► planner ─► researcher/tool-router ─► code_writer ─► reviewer ─► write_gate(interrupt)
                              │                                       │
                              │ emits proposed_reads[]                │ emits proposed_writes[]
                              ▼                                       ▼
                       OrchestrationResult { summary, proposed_reads[], proposed_writes[], evidence[] }
                              │                                       │
                              ▼ (NEW, ungated)                        ▼ (existing, approval-gated)
   ┌──────────────────────────────────────────────┐    ┌─────────────────────────────────────────┐
   │ Worker.process: execute reads immediately     │    │ Worker: ToolCall(AWAITING_APPROVAL) →     │
   │  ToolCall(category=read) → gateway.execute()   │    │ approval ledger (payload-hash) → pause →  │
   │  → record EXECUTED → append to evidence        │    │ resume → is_approved() → gateway.execute()│
   └───────────────────────┬──────────────────────┘    └──────────────────┬──────────────────────┘
                           │                                               │
                           ▼                 ToolGateway.execute(call)      ▼
        ┌──────────────────────────────────────────────────────────────────────────┐
        │ 1. CredentialResolver.resolve(spec.credential_secret_name)  (env → SM)     │
        │ 2. SchemaValidator.validate_input(spec, params)   [direct: our schema;     │
        │      aggregate: runtime provider schema; D-04 fail-closed direct-only]     │
        │      └─ input invalid → HARD REJECT, no SaaS call, failed tool_call (D-06) │
        │ 3. adapter dispatch by integration_style:                                  │
        │      direct_api → hubspot-api-client / google-api-python-client            │
        │      composio_aggregator / aggregate_mcp → composio SDK session.tools()    │
        │      nango_aggregator → httpx GET/POST {NANGO_HOST}/proxy + headers        │
        │ 4. SchemaValidator.validate_output(spec, result)                           │
        │      └─ output invalid → FLAG/QUARANTINE + record, halt downstream (D-06)  │
        │ 5. emit OTel tool span (tool,provider,category,integration_style,latency,  │
        │      approval_state,outcome) via observability.get_tracer (D-10)           │
        └──────────────────────────────────────────────────────────────────────────┘
                           │                                   │
                  (creds absent for provider)                  ▼
                  └────────► deterministic STUB result ◄── tool_calls table (tenant-scoped, DUR-02)
```

### Component Responsibilities
| File | Change | Audit item |
|------|--------|-----------|
| `tools/gateway.py` | `ToolSpec` gains `integration_style`, `input_schema_ref`, `output_schema_ref` (D-03); `execute()` becomes the real engine taking a `ToolCall`/context; add `CredentialResolver`, `SchemaValidator`, adapter dispatch | D-03/D-02/D-04/D-10 |
| `worker/orchestrator.py` | `OrchestrationResult` gains `proposed_reads: list[dict]`; `_run_stub` emits a deterministic read so the default lane exercises the path | **A** |
| `worker/graph.py` | researcher node emits `proposed_reads` (heuristic in stub lane, plan-derived with creds); reviewer keeps `proposed_writes` heuristic; replace hardcoded stub write with plan-derived selection | **A/C** |
| `worker/runner.py` | Execute `proposed_reads` ungated post-`run_mesh` (record `category=read` ToolCalls, append to evidence); `_execute` passes the `ToolCall` to `gateway.execute()` | **A/B** |
| `worker/main.py` | Build `Worker(tool_gateway=ToolGateway.from_manifest(...))` + a `CredentialResolver` | **B** |
| `contracts/models.py` | `ToolCall` gains additive optional fields: `integration_style: str|None`, `schema_validation: str|None` (e.g. `"input_rejected"`/`"output_quarantined"`/`"ok"`), `is_read: bool=False`; regenerate `schemas/contracts/ToolCall.schema.json` | **D** |
| `observability.py` | add a `tool_event_span(...)` helper (or reuse `get_tracer`+`set_span_metadata`) | **E/D-10** |
| `pyproject.toml` | add `tools` + `aggregators` extras; `jsonschema` to core deps | D-12 prep |

### Pattern 1: CredentialResolver (Secret-Manager-shaped, env-backed)
**What:** A small abstraction keyed by the manifest's `credential_secret_name`. Local backend reads `os.environ[name]`; prod backend swaps to Secret Manager. Resolves only inside `execute()` — never returned to the graph/agent (D-02).
**When to use:** Every adapter call that needs a credential.
```python
# tools/credentials.py  (new) — Source: pattern derived from settings/observability lazy-import style
from __future__ import annotations
import os
from typing import Protocol

class CredentialResolver(Protocol):
    def resolve(self, secret_name: str | None) -> str | None: ...

class EnvCredentialResolver:
    """Local, creds-free-by-default. Returns None when the env var is absent so the
    adapter degrades to the deterministic stub (D-11)."""
    def resolve(self, secret_name: str | None) -> str | None:
        if not secret_name:
            return None
        return os.getenv(secret_name)  # e.g. HUBSPOT_PRIVATE_APP_TOKEN, GOOGLE_WORKSPACE_OAUTH

# Prod swap (not built this phase, documented seam):
# class SecretManagerResolver: resolve() -> google-cloud-secret-manager access_secret_version
```
> For Google Workspace the single `credential_secret_name: GOOGLE_WORKSPACE_OAUTH` should resolve to a JSON blob `{client_id, client_secret, refresh_token}` (the unattended-refresh material), not a single token. Document this shape in D-12's setup doc.

### Pattern 2: SchemaValidator — Draft 2020-12, asymmetric failure (D-04/05/06)
**What:** Loads `input_schema_ref`/`output_schema_ref` for direct tools; fetches the provider schema at runtime for aggregate tools. Validates input pre-call, output post-call.
```python
# tools/validation.py  (new) — Source: jsonschema 4.26 verified locally (Draft202012Validator)
from __future__ import annotations
import json
from pathlib import Path
from jsonschema import Draft202012Validator

class SchemaError(Exception): ...
class InputSchemaViolation(SchemaError): ...     # → hard reject, no SaaS call (D-06)
class OutputSchemaViolation(SchemaError): ...     # → quarantine + record, halt trust (D-06)

def _load(ref: str) -> dict:
    return json.loads(Path(ref).read_text())

def validate_input(schema: dict | None, params: dict) -> None:
    if schema is None:
        # D-04 fail-closed applies to DIRECT tools only; the caller decides whether a
        # missing schema is "blocked" (direct) or "skip — runtime schema" (aggregate).
        raise InputSchemaViolation("no input schema declared")
    errs = sorted(Draft202012Validator(schema).iter_errors(params), key=lambda e: list(e.path))
    if errs:
        raise InputSchemaViolation("; ".join(e.message for e in errs))

def validate_output(schema: dict | None, result: dict) -> list[str]:
    if schema is None:
        return []  # permissive: nothing to check
    return [e.message for e in Draft202012Validator(schema).iter_errors(result)]
```
**Fail-closed dispatch (the D-04 nuance — do NOT generalize):**
```python
if spec.integration_style == "direct_api":
    if spec.input_schema_ref is None:
        raise InputSchemaViolation(f"{spec.name}: direct tool with no schema is BLOCKED")  # D-04
    validate_input(_load(spec.input_schema_ref), params)
else:  # composio_aggregator / nango_aggregator / aggregate_mcp
    runtime_schema = fetch_runtime_schema(spec)   # may be None — NEVER blocks (D-04)
    if runtime_schema is not None:
        validate_input(runtime_schema, params)
```
**Asymmetric outcome → tool_call row (D-06):**
- Input violation: set `ToolCall.status = FAILED`, `schema_validation = "input_rejected"`, `result = {"error": msg}`, **no adapter call**, persist row, raise.
- Output violation: adapter already ran; set `status = EXECUTED` (it did run) but `schema_validation = "output_quarantined"`, store `result` with a quarantine flag, do not feed it into downstream evidence as trusted. (Distinguish "ran but untrusted" from "never ran".)

### Pattern 3: Runtime aggregate-schema fetch + cache
**What:** Composio/Nango expose per-tool JSON Schemas; we cannot hand-author ~982 (D-04). Fetch at first use, cache in-process keyed by `(provider, tool_slug)`.
```python
# Composio: session.tools() returns tool defs carrying input JSON Schema
from composio import Composio
def fetch_composio_schema(session, tool_slug: str) -> dict | None:
    for t in session.tools():               # Source: docs.composio.dev quickstart
        if t.get("name") == tool_slug or t.get("slug") == tool_slug:
            return t.get("input_parameters") or t.get("inputSchema")  # verify exact key at impl
    return None

# Nango: no per-tool JSON Schema from the proxy; treat as permissive (runtime_schema=None → no block)
# Cache: a module-level dict guarded for the process; invalidate on TTL or never (POC).
_SCHEMA_CACHE: dict[tuple[str, str], dict | None] = {}
```
> **Planner decision flagged:** Composio's exact schema key on the tool def (`input_parameters` vs `inputSchema` vs nested) is not pinned from docs — confirm at implementation with one live `session.tools()` dump. Nango proxy returns no schema, so the Nango read is validated permissively (its `runtime_schema` is `None`, which D-04 says NEVER blocks for aggregate).

### Anti-Patterns to Avoid
- **Passing resolved credentials into the graph/agent state.** Resolve only inside `execute()` (D-02). The graph nodes must stay creds-free and stub-degradable.
- **Installing the PyPI `nango` package.** It is not the official client. Use `httpx` to the Nango proxy.
- **Applying fail-closed to aggregate tools.** A missing schema blocks direct tools only (D-04). Aggregate schema arrives at runtime; absence is permissive.
- **Rewriting the `ToolCall` contract.** Additive optional fields only (D); the P1 ledger + payload-hash and existing rows must keep validating (`extra="forbid"` + a contract/schema-parity test exist).
- **Executing reads through the approval gate.** Reads are ungated (A); routing them through `is_approved()` would break the read path and is semantically wrong.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON-Schema validation | A custom required/type checker | `jsonschema` `Draft202012Validator` | Matches the `$schema` already in the schema files; handles enums/bounds/`additionalProperties` correctly |
| Google OAuth token refresh | Manual token POST + expiry bookkeeping | `google.oauth2.credentials.Credentials(refresh_token=...)` | Auto-refreshes on expiry; official, unattended-safe |
| HubSpot REST plumbing | Hand-built search/create bodies + retry | `hubspot-api-client` (or thin `httpx` if preferred) | Typed object/search models; one bearer token |
| Nango unified-API call | Re-implementing Nango's auth injection | Nango **proxy** REST endpoint via `httpx` | Nango injects creds + handles rate-limit/retry server-side |
| Composio managed auth | OAuth flows per SaaS | `composio` SDK `Composio().create(user_id)` + `session.tools()` | Managed auth is Composio's whole value; do not re-broker |
| OTel tool span transport | New exporter/provider | `observability.get_tracer()` + `set_span_metadata()` | Phase-3 transport already built + test-injectable |

**Key insight:** This phase is almost entirely *integration*, not invention. Every hard part (auth, schema validation, span transport, approval gate, tenant scoping, stub fallback) already has a blessed library or an existing seam. The only genuinely new design is the `proposed_reads` execution path.

## Runtime State Inventory

Not a rename/refactor/migration phase — net-new adapters + additive contract fields only.
- **Stored data:** None affected. New `tool_calls` rows (reads + schema-reject rows) are additive; existing rows keep validating. Verified by reading `contracts/models.ToolCall` (additive optional fields with defaults).
- **Live service config:** None — no external service registrations created this phase (live lane is opt-in, creds supplied by the user per D-12).
- **OS-registered state:** None.
- **Secrets/env vars:** New env var **names** introduced for the local live lane (`HUBSPOT_PRIVATE_APP_TOKEN`, `GOOGLE_WORKSPACE_OAUTH`, `COMPOSIO_API_KEY`, `NANGO_SECRET_KEY`/`NANGO_HOST`/`NANGO_CONNECTION_ID`/`NANGO_PROVIDER_CONFIG_KEY`). These align with the manifest's existing `credential_secret_name` values (`HUBSPOT_PRIVATE_APP_TOKEN`, `GOOGLE_WORKSPACE_OAUTH`). No code reads them unless the live lane runs. Documented in D-12 setup doc.
- **Build artifacts:** `schemas/contracts/ToolCall.schema.json` is regenerated by the exporter after the additive `ToolCall` fields land — must re-run the schema export and keep the parity test green.

## Common Pitfalls

### Pitfall 1: Nango Python "SDK" that isn't
**What goes wrong:** `pip install nango` succeeds (0.1.2 exists) but it is not the official client; you wire a fake API and the Nango live read never works.
**Why it happens:** Cross-ecosystem confusion — Nango's only SDK is npm `@nangohq/node`. The Python path is the REST proxy.
**How to avoid:** Call `{NANGO_HOST}/proxy` with `httpx`, headers `Authorization: Bearer <secret>`, `Connection-Id`, `Provider-Config-Key`, and a `endpoint`/method param. Self-host Nango via its `docker-compose.yaml` for the local live lane.
**Warning signs:** Any import of a `nango` Python package in a plan.

### Pitfall 2: `execute()` signature can't carry correlation
**What goes wrong:** Keeping `execute(name, parameters)` means the D-10 span has no `task_id`/`tenant_id`, the cred resolver has no tenant context, and the failed-`tool_call` row can't be built.
**Why it happens:** The stub signature predates the real engine.
**How to avoid:** Change to `execute(call: ToolCall, *, resolver, ...) -> dict` (or pass a small `ToolContext`). `runner._execute` already holds the `ToolCall` — pass it through. Update the one stub call site in `runner.py`.
**Warning signs:** Span attributes missing tenant/task; resolver reaching into globals.

### Pitfall 3: Composio is a 0.x package with name/API churn
**What goes wrong:** A plan pins `composio-core` (old name) or assumes `session.tools()` returns a particular schema key; it breaks at install.
**How to avoid:** Pin `composio>=0.13,<1`; confirm `from composio import Composio` and the exact tool-schema key with one live `session.tools()` dump at implementation. Gate behind `checkpoint:human-verify`.

### Pitfall 4: Google "full suite live" implies authoring ~6 products of manifest + schemas (D-08 × D-04)
**What goes wrong:** Only `google_drive_search` has schemas today; `gmail_send`/`google_sheets_append` have none, and Calendar/Docs/Slides aren't in the manifest. Fail-closed-for-direct (D-04) means **every** GWS direct tool needs a manifest entry + input/output schema or it is blocked.
**How to avoid:** Treat **adapter + manifest entry + input schema + output schema** as one unit per product (a per-product plan split, per CONTEXT D-08). Permissive schemas (D-05): required + types, `additionalProperties` allowed except on cost/security-critical write fields.
**Warning signs:** A plan that adds a GWS adapter without the matching schema files — it will be blocked at the boundary.

### Pitfall 5: Schema-reject test must use a tool that DOES declare schemas
**What goes wrong:** The D-06 deterministic reject test (success criterion #2, default lane) accidentally targets a schema-less tool, so it tests "no schema" not "schema rejects bad input."
**How to avoid:** Point the default-lane reject test at `hubspot_lookup_company` or `google_drive_search` (both have input schemas with `required`/`enum`/`additionalProperties:false`) and feed it a payload that violates the schema. Assert hard reject + no adapter call + failed `tool_call` row. (Verified locally: `Draft202012Validator` flags `'a' is a required property`.)

### Pitfall 6: HubSpot writes hitting production
**What goes wrong:** `hubspot_create_deal` live test mutates a real pipeline.
**How to avoid:** Use a HubSpot **standard sandbox** (Settings → Account Management → Sandboxes) or a free **developer test account**; sandbox object IDs differ from production, so set `resource_bindings.pipeline_id` to the sandbox pipeline. Document in D-12.

## Code Examples

### HubSpot — lookup (read) and create deal (write)
```python
# Source: developers.hubspot.com — hubspot-api-client 12.x; scopes verified below
from hubspot import HubSpot
client = HubSpot(access_token=token)  # token = CredentialResolver.resolve("HUBSPOT_PRIVATE_APP_TOKEN")

# READ: hubspot_lookup_company → CRM Search API
from hubspot.crm.companies import PublicObjectSearchRequest
res = client.crm.companies.search_api.do_search(
    public_object_search_request=PublicObjectSearchRequest(
        query=params["query"], limit=params.get("limit", 5),
    )
)
# map → {"records": [{"id": o.id, "properties": o.properties} ...]}  (matches output schema)

# WRITE (approval-gated): hubspot_create_deal → CRM objects API
from hubspot.crm.deals import SimplePublicObjectInputForCreate
deal = client.crm.deals.basic_api.create(
    simple_public_object_input_for_create=SimplePublicObjectInputForCreate(
        properties={"dealname": params["deal_name"], "dealstage": params["stage"]}
    )
)
# map → {"deal_id": deal.id, "status": "created", "pipeline_id": ...}
```
**Exact HubSpot scopes** `[CITED: developers.hubspot.com]`:
- read: `crm.objects.companies.read`, `crm.objects.contacts.read`
- write: `crm.objects.deals.write` (and `crm.objects.deals.read` if reading deals back)

### Google Workspace — one client, refresh-token creds (unattended live lane)
```python
# Source: googleapis/google-api-python-client + google-auth
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

blob = json.loads(resolver.resolve("GOOGLE_WORKSPACE_OAUTH"))  # {client_id, client_secret, refresh_token}
creds = Credentials(
    token=None,
    refresh_token=blob["refresh_token"],
    token_uri="https://oauth2.googleapis.com/token",
    client_id=blob["client_id"],
    client_secret=blob["client_secret"],
    scopes=[...],  # the union of per-product scopes below
)  # auto-refreshes on first call

drive = build("drive", "v3", credentials=creds)          # google_drive_search (read)
gmail = build("gmail", "v1", credentials=creds)          # gmail_send (external_send, gated)
sheets = build("sheets", "v4", credentials=creds)        # google_sheets_append (write, gated)
calendar = build("calendar", "v3", credentials=creds)    # calendar read + create (gated)
docs = build("docs", "v1", credentials=creds)            # docs read + write (gated)
slides = build("slides", "v1", credentials=creds)        # slides read + write (gated)
```
**Exact Google scopes** `[CITED: developers.google.com/identity/protocols/oauth2/scopes]`:
| Product | Read scope | Write/send scope |
|---------|-----------|------------------|
| Drive | `https://www.googleapis.com/auth/drive.readonly` | `https://www.googleapis.com/auth/drive.file` |
| Gmail | — | `https://www.googleapis.com/auth/gmail.send` |
| Calendar | `https://www.googleapis.com/auth/calendar.readonly` | `https://www.googleapis.com/auth/calendar.events` |
| Sheets | `https://www.googleapis.com/auth/spreadsheets.readonly` | `https://www.googleapis.com/auth/spreadsheets` |
| Docs | `https://www.googleapis.com/auth/documents.readonly` | `https://www.googleapis.com/auth/documents` |
| Slides | `https://www.googleapis.com/auth/presentations.readonly` | `https://www.googleapis.com/auth/presentations` |

**Refresh-token minting (one-time, for the D-12 doc, NOT in the live test path):** `google-auth-oauthlib` `InstalledAppFlow.from_client_secrets_file(..., scopes).run_local_server(access_type="offline", prompt="consent")` → store `creds.refresh_token` into the `GOOGLE_WORKSPACE_OAUTH` blob. The refresh token is long-lived; rotation = re-run the consent flow.

### Composio — managed auth + one real read (aggregator primary)
```python
# Source: docs.composio.dev/getting-started/quickstart  (composio 0.13.x)
from composio import Composio
composio = Composio()                      # reads COMPOSIO_API_KEY from env
session = composio.create(user_id="mesh-tenant-example")  # managed auth / connected account
tools = session.tools()                    # tool defs incl. input JSON Schema (runtime schema, D-04)
result = session.execute(tool="<read_tool_slug>", arguments={...})  # confirm exact execute API at impl
# MCP Tool Router alternative: session.mcp.url + session.mcp.headers (Phase-5 breadth)
```

### Nango — REST proxy + one real read (aggregator fallback, NO python SDK)
```python
# Source: github.com/NangoHQ/nango (SDK is @nangohq/node only) — Python via httpx proxy
import httpx
resp = httpx.request(
    "GET",
    f"{os.environ['NANGO_HOST']}/proxy/<provider-endpoint-path>",  # e.g. /proxy/v3/contacts
    headers={
        "Authorization": f"Bearer {os.environ['NANGO_SECRET_KEY']}",
        "Connection-Id": os.environ["NANGO_CONNECTION_ID"],
        "Provider-Config-Key": os.environ["NANGO_PROVIDER_CONFIG_KEY"],
    },
    timeout=30,
)
# Self-host for the local live lane:
#   mkdir nango && cd nango && wget <docker-compose.yaml from NangoHQ/nango master> && docker compose up -d
```

### Tool-event OTel span (closes OBS-01 / D-10)
```python
# Source: observability.py get_tracer/set_span_metadata (Phase 3 transport, verified)
from agent_mesh import observability as obs
tracer = obs.get_tracer()
if tracer is not None:
    with tracer.start_as_current_span("tool.execute") as span:
        obs.set_span_metadata(span, task_trace_metadata)  # tenant/task/session/requester correlation
        span.set_attribute("tool", spec.name)
        span.set_attribute("provider", spec.provider)
        span.set_attribute("category", spec.category.value)
        span.set_attribute("integration_style", spec.integration_style)
        span.set_attribute("approval_state", approval_state)
        span.set_attribute("outcome", outcome)  # ok | input_rejected | output_quarantined | stub | error
# No-op when OTel absent (default-suite-safe). NEVER set raw creds or full payloads as attributes.
```

## Recommended read-execution seam (audit item A — the plan-shaping decision)

**Recommendation: Option 1 — post-run ungated reads mirroring the write path.**

- `OrchestrationResult` gains `proposed_reads: list[dict]` (same shape as `proposed_writes`: `{tool_name, category:"read", parameters}`).
- The researcher node emits `proposed_reads` (deterministic in the stub lane — e.g. a `hubspot_lookup_company`/`google_drive_search` read derived from the prompt — so the default lane exercises the read path creds-free, mirroring how `_run_stub` proposes a write).
- After `run_mesh`, **before** the write-gate branch, `Worker.process` iterates `proposed_reads`, builds `ToolCall(category=read, approval_required=False, status=EXECUTED-after-run)`, calls `gateway.execute(call)` **immediately and ungated**, records the row (tenant-scoped, DUR-02), and appends results to `evidence`.
- Reuses the existing `gateway is None → stub` fallback in `runner._execute` unchanged. No approval-ledger involvement. No gateway injection into creds-gated graph nodes.

> **Real-graph wrinkle the implementer must check (flag for planner):** on the LangGraph path, `_run_langgraph` extracts `proposed_writes` from `final_state["__interrupt__"][0].value` when a write pauses the run. Reads emitted by the researcher node are *accumulated channel state*, not part of the interrupt payload — confirm whether `compiled.invoke` returns accumulated `proposed_reads` ALONGSIDE `__interrupt__`, or only the interrupt value. If only the latter, surface `proposed_reads` in BOTH branches of `_run_langgraph` (or execute reads before the write gate). The stub/default lane has no interrupt, so the green-suite story holds regardless; this is a real-path-only detail.
> **Evidence is `list[str]`:** read results are dicts, but `OrchestrationResult.evidence` is `list[str]`. Append a string summary/source-pointer (or persist an `EvidenceChunk` and reference it), not the raw dict.

**Trade-off / limitation (state honestly to the planner):** This proves the **read execution path + both integration styles end-to-end**, which is exactly TOOL-01/TOOL-04's bar. It does **not** give *reactive in-loop tool use* (a read result informing a same-run write within the graph) — that requires the gateway inside the researcher node and is a larger orchestration concern. Recommend deferring reactive in-loop reads (note for Phase 5/later); Phase 4 delivers post-run ungated reads. This framing serves D-01 ("viable general functionality") better than pretending the post-run path is a reactive agent.

**Option 2 (in-graph reads) — rejected for Phase 4:** researcher node calls `gateway.execute()` directly so reads feed reasoning. More faithful to a real agent loop but pushes the gateway + cred resolution into creds-gated nodes that currently degrade to stub, enlarging the blast radius and muddying the no-creds→stub line (D-11). Bigger change, not required by the phase requirements.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Composio `composio-core` package | `composio` package, `from composio import Composio`, session/Tool-Router model | Composio Tool Router GA 2026-05 (Spike 001) | Pin `composio>=0.13,<1`; confirm import at impl |
| Nango "use the SDK" | Nango has **no Python SDK**; REST proxy is the Python path | ongoing — SDK is `@nangohq/node` | Use `httpx`, not a `nango` pip package |
| Hand-rolled schema checks | `jsonschema` Draft 2020-12 | matches existing schema `$schema` | Zero schema rewrites needed |

**Deprecated/outdated:**
- PyPI `nango` 0.1.2 as "the Nango client" — not official; avoid.
- Composio `composio-core` import path — superseded by `composio`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `composio` 0.13.1 SDK exposes `session.tools()` with per-tool input JSON Schema under a key like `input_parameters`/`inputSchema` | Pattern 3, Composio example | Aggregate runtime-schema validation key wrong → confirm with one `session.tools()` dump at impl |
| A2 | `composio` `session.execute(tool=..., arguments=...)` is the read-call API | Composio example | Exact execute method name may differ in 0.13.x — verify at impl |
| A3 | Nango proxy path is `{NANGO_HOST}/proxy/<endpoint>` with `Connection-Id`/`Provider-Config-Key` headers | Nango example | Header/path casing may differ; confirm against running self-host instance |
| A4 | `hubspot-api-client` 12.x search/create method names (`search_api.do_search`, `basic_api.create`) | HubSpot example | Method names stable across 11–12 but verify; raw REST is the fallback |
| A5 | `GOOGLE_WORKSPACE_OAUTH` resolves to a `{client_id, client_secret, refresh_token}` JSON blob | CredentialResolver, Google example | If a different cred shape is chosen, adjust resolver + D-12 doc |
| A6 | All package version pins (`[ASSUMED]` — slopcheck unavailable) | Standard Stack, Audit | Slopsquat/version risk → planner gates each behind `checkpoint:human-verify` |
| A7 | Drive write op uses `drive.file` scope (least-privilege) vs full `drive` | Google scopes table | If broad Drive write needed, use `https://www.googleapis.com/auth/drive` |

## Open Questions

1. **Per-product GWS operation set (read + key writes).**
   - What we know: full suite live (D-08); reads ungated, writes/sends gated.
   - What's unclear: exactly which write op per product (e.g. Calendar create-event vs update; Docs create vs batchUpdate).
   - Recommendation: planner picks one representative read + one representative write per product; size as one plan unit per product (adapter+manifest+2 schemas).
2. **`jsonschema` placement: core dep vs `tools` extra.**
   - Recommendation: core dep (small, pure, no creds) so the schema boundary is never an optional import; provider SDKs stay extras.
3. **Composio user_id / connected-account model for one tenant.**
   - Recommendation: use `composio.create(user_id="<tenant_slug>")`; the managed-auth connection is set up once via the D-12 doc.

## Environment Availability

| Dependency | Required By | Available locally | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `jsonschema` | TOOL-02 boundary | ✓ | 4.26.0 | none needed (core) |
| `hubspot-api-client` | HubSpot live lane | ✗ (extra) | 12.0.0 (PyPI) | raw `httpx`; stub when no token |
| `google-api-python-client` | GWS live lane | ✗ (extra) | 2.197.0 (PyPI) | stub when no creds |
| `composio` | Composio live lane | ✗ (extra) | 0.13.1 (PyPI) | stub when no `COMPOSIO_API_KEY` |
| Docker (Nango self-host) | Nango live lane | ? (check at impl) | — | skip Nango live test when host absent (D-11) |
| `httpx` | Nango proxy | ✓ (core) | already pinned | — |

**Missing dependencies with no fallback:** None — every provider degrades to the deterministic stub when its creds/host are absent (D-11). Nango live lane additionally needs a running self-hosted instance; absence simply skips that one live test.

## Validation Architecture

> Nyquist is disabled this run, but a test-strategy map helps the planner. Reuses the established `@pytest.mark.live` + creds-present-skip pattern (`tests/test_cascade_live.py`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x (`[tool.pytest.ini_options]`, `pythonpath=["src"]`) |
| Live marker | `@pytest.mark.live` (deselected by default; `make test` runs `-m "not live"`) |
| Quick run | `make test` (default lane, creds-free, must stay green) |
| Live run | `make test-live` (`pytest -m live`) |

### Requirements → Test Map
| Req | Behavior | Test type | Command | Lane |
|-----|----------|-----------|---------|------|
| TOOL-01 | Cred resolved at execute time; agent never holds it | unit | `pytest tests/test_gateway_engine.py -x` | default (stub) + assert resolver only called in execute |
| TOOL-01 | HubSpot lookup real call | live | `pytest -m live tests/test_hubspot_live.py` | skip if no `HUBSPOT_PRIVATE_APP_TOKEN` |
| TOOL-01 | GWS Drive search real call | live | `pytest -m live tests/test_gws_live.py` | skip if no `GOOGLE_WORKSPACE_OAUTH` |
| TOOL-02 | Input violation → hard reject, no call, failed row | unit | `pytest tests/test_schema_boundary.py::test_input_reject -x` | default — use `hubspot_lookup_company` (has schema) |
| TOOL-02 | Output violation → quarantine + record, halt trust | unit | `pytest tests/test_schema_boundary.py::test_output_quarantine -x` | default |
| TOOL-02 | Direct tool, no schema → blocked (fail-closed) | unit | `pytest tests/test_schema_boundary.py::test_direct_no_schema_blocked -x` | default |
| TOOL-02 | Aggregate tool, no runtime schema → NOT blocked | unit | `pytest tests/test_schema_boundary.py::test_aggregate_no_schema_permissive -x` | default |
| TOOL-04 | Composio one real read end-to-end | live | `pytest -m live tests/test_composio_live.py` | skip if no `COMPOSIO_API_KEY` |
| TOOL-04 | Nango one real read end-to-end | live | `pytest -m live tests/test_nango_live.py` | skip if no `NANGO_*` + host |
| OBS-01 | Tool-event span emitted with correlation keys | unit | `pytest tests/test_tool_span.py -x` (inject in-memory exporter) | default |
| A (read seam) | `proposed_reads` execute ungated, record read ToolCalls, feed evidence | unit | `pytest tests/test_read_path.py -x` | default (stub gateway) |
| D-07 write | `hubspot_create_deal` still gated through ledger | unit | reuse existing approval suite + new gateway | default |

### Wave 0 Gaps
- [ ] `tests/test_gateway_engine.py` — engine: cred resolution + dispatch + stub fallback
- [ ] `tests/test_schema_boundary.py` — the four D-04/D-06 cases above (must use schema-declaring tools for reject)
- [ ] `tests/test_read_path.py` — `proposed_reads` ungated execution (item A)
- [ ] `tests/test_tool_span.py` — OBS-01/D-10 span (reuse in-memory exporter seam from Phase-3 conftest)
- [ ] `tests/test_{hubspot,gws,composio,nango}_live.py` — per-provider live lane, each `@pytest.mark.live` + own creds-present skip
- [ ] Regenerate `schemas/contracts/ToolCall.schema.json` after additive fields; keep the contract/schema-parity test green

## Project Constraints (from CLAUDE.md)

- **Required stack** LangChain/LangGraph/Deep Agents/Langfuse; LangSmith never a dependency. (Phase 4 adds no model deps; reuses Phase-3 gateway/observability.)
- **Agents never receive raw credentials** — Tool Gateway resolves at execution time only (§2/§3/§5). Hard constraint on `CredentialResolver`.
- **All write-class tools require approval** via the shared ledger, payload-hash bound (§6 #11). `hubspot_create_deal` + every GWS write/send stays gated; do not weaken SEC-01/02.
- **Toolpack declares providers each with an integration style** (§6 #12/#13); Composio + Nango are peer aggregator options (#13). Honour the manifest's `integration_style`.
- **Observability is Langfuse-centered** (§6 #16) — tool spans land via the OTel transport (D-10).
- **No runtime autonomous self-modification** (§8) — not in scope this phase.
- **Stub-fallback degradation** — `make test`/`make smoke` stay green and creds-free (§8 / D-11).

## Sources

### Primary (HIGH confidence)
- Codebase: `tools/gateway.py`, `worker/{orchestrator,graph,runner,main}.py`, `services/{approvals,repository}.py`, `observability.py`, `contracts/{enums,models}.py`, `manifests/tool_pack_manifest.yaml`, `schemas/*.json`, `tests/test_cascade_live.py`, `pyproject.toml`, `Makefile` — read in full this session.
- Local verification: `jsonschema` 4.26.0 `Draft202012Validator` validates required fields (ran locally); `pip index versions` for all candidate packages.
- developers.google.com/identity/protocols/oauth2/scopes — exact Google scope URLs.
- github.com/NangoHQ/nango — confirms SDK is `@nangohq/node` only; REST proxy is the Python path.
- docs.composio.dev/getting-started/quickstart — `from composio import Composio`, `session.tools()`, `session.mcp.url`.

### Secondary (MEDIUM confidence)
- developers.hubspot.com (private apps overview + scopes) — `crm.objects.*.read/write` scope strings; private-app token flow.
- knowledge.hubspot.com — standard sandbox setup for non-production writes.
- google-api-python-client GitHub issue #213 + syncwithtech.org — refresh-token `Credentials(...)` unattended flow.
- nango.dev/docs (self-host configuration) — `docker-compose.yaml` self-host; `/proxy` REST shape.
- `.planning/spikes/001-composio-vs-nango-coverage/README.md` — D-09 rationale (Composio MCP-native primary, Nango OSS fallback).

### Tertiary (LOW confidence — verify at implementation)
- Exact Composio `session.tools()` schema key and `session.execute` API (A1/A2).
- Exact Nango proxy path/header casing against a running instance (A3).
- `hubspot-api-client` 12.x exact method names (A4).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions from PyPI; package names from official docs (Nango correction is the key finding).
- Read-execution seam (A): HIGH — derived directly from read code; recommendation + trade-off stated.
- Schema boundary: HIGH — jsonschema verified locally against the on-disk Draft-2020-12 schemas.
- Provider call APIs: MEDIUM — entry points cited; exact method/key names flagged for impl-time confirmation.
- Package legitimacy: MEDIUM — slopcheck unavailable; mitigated by official-doc cross-ref + mandatory human-verify gate.

**Research date:** 2026-06-06
**Valid until:** ~2026-07-06 for stable libs (Google/HubSpot/jsonschema); ~2026-06-20 for Composio (0.x, fast-moving) and Nango self-host.
