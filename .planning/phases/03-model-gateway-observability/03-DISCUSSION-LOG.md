# Phase 3: Model Gateway & Observability - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-06
**Phase:** 3-model-gateway-observability
**Areas discussed:** Live ceiling, Budget enforcement, Cloudflare never-bypass, Langfuse correlation, Gateway shape

---

## Live local-validation ceiling

The first question (faked boundary vs real provider) was **rejected/clarified** by the user, who
directed: **"Real Router + Real Provider."** Reformulated to ask how that coexists with the green suite.

### Q1 — Live lane vs green-suite constraint
| Option | Description | Selected |
|--------|-------------|----------|
| Opt-in live lane | Default make test/smoke stub-green; separate `make test-live`/`pytest -m live` drives real Router → real providers, tiny budget cap | ✓ |
| One suite, auto-skip | Same tests in default suite, auto-skip when no creds | |
| Real provider IS default | make test requires creds, calls real providers (breaks no-cloud-deps) | |

**User's choice:** Opt-in live lane.
**Notes:** Real Router → Real Provider was a hard user directive replacing the original faked-boundary option.

### Q2 — Which providers live
| Option | Description | Selected |
|--------|-------------|----------|
| Anthropic live, Vertex structural | Real Anthropic only; Vertex route resolves but not called | |
| Both live | Real Anthropic AND Vertex; cross-provider cascade (Vertex→fail→Anthropic) | ✓ |
| You decide | Defer provider-liveness to research | |

**User's choice:** Both live.
**Notes:** User has Vertex/GCP creds. Live Vertex *model call* ≠ GCP infra provisioning — respects milestone.

---

## Budget enforcement model

### Q1 — Enforcement point + durability
| Option | Description | Selected |
|--------|-------------|----------|
| Durable ledger halts, gateway backs | Postgres budget_ledger pre-call check/post-call record halts run; LiteLLM max_budget prod hard-stop | ✓ |
| Gateway-only | Rely on LiteLLM max_budget; ledger is passive audit mirror | |
| In-memory only | Keep in-process dict; resets on restart | |

**User's choice:** Durable ledger halts, gateway backs.
**Notes:** Tightened post-advisor — in the in-process Router runtime (D-09) the ledger is the SOLE enforcer; max_budget inert until proxy scale-up deployed.

### Q2 — Per-user vs per-task scope
| Option | Description | Selected |
|--------|-------------|----------|
| Per-user halts, per-task attributes | $50/mo per-user hard cap halts; per-task tagged for attribution + optional ceiling | ✓ |
| Both hard caps | Independent per-user AND per-task caps, both halt | |
| Per-user only (v1) | Only per-user cap; per-task not tracked as budget dimension | |

**User's choice:** Per-user halts, per-task attributes.

---

## Cloudflare never-bypass proof

### Q1 — Local proof of GW-02
| Option | Description | Selected |
|--------|-------------|----------|
| Structural guard + config | Egress chokepoint (get_chat_model only) + guard test + config assertion; real CF traversal opt-in in live lane | ✓ |
| Real CF mandatory in live lane | Deployed CF required; real call must traverse it (overlaps DEP-02/Phase 5) | |
| Config-only | Assert yaml/wrangler only; no code guard | |

**User's choice:** Structural guard + config.
**Notes:** CF stays integration-ready (CLAUDE.md #6); wrangler publish/dry-run is Phase 5.

---

## Langfuse correlation

The OTel-first option was **refined** by the user mid-selection.

### Q1 — Trace backbone + non-model event correlation
| Option | Description | Selected |
|--------|-------------|----------|
| Langfuse-native, one trace/task | Callback for model spans + Langfuse SDK spans for tool/approval | |
| OTel-first / OTLP | All events as OTel spans → OTLP → Langfuse; metadata as span attrs | ✓ (refined) |
| Callback-only (model spans) | Model spans only; tool/approval deferred | |

**User's choice:** OTel-first / OTLP — **with the refinement:** Langfuse is the **default** OTLP
consumer, but the operator can **replace it or run another consuming SIEM in parallel** (multi-exporter).
**Notes:** Captured explicitly that "replaceable/parallel ≠ Langfuse optional" — Langfuse stays REQUIRED
(it is also the OBS-02 prompt/eval plane, which OTel does not cover). trace_id per task set on
OrchestrationResult (closes P2 gap). In-memory OTel exporter for deterministic CI proof.

### Q2 — OBS-02 depth
| Option | Description | Selected |
|--------|-------------|----------|
| Thin / seeded | Versioned prompt + fetch-or-fallback + 1 seeded dataset + example eval; real harness → P4 | ✓ |
| Deeper (real eval now) | Real LLM-judge eval run (overlaps P4 SI-01) | |
| Config-only | Keys/host + docs only | |

**User's choice:** Thin / seeded.

---

## Gateway shape (added gray area)

The first framing was **rejected/clarified** — user asked whether a single proxy in front of the edge
gateway is a SPOF, making litellm.Router more viable/controllable. Answered with SPOF analysis
(self-run proxy = second self-operated chokepoint; CF is managed/HA), then reformulated.

### Q1 — Proxy status given in-process Router runtime
| Option | Description | Selected |
|--------|-------------|----------|
| Deploy-validated scale-up path | In-process Router runtime; proxy yaml schema/lint validated + api_base seam preserved for prod | ✓ |
| Drop proxy entirely (v1) | In-process Router only; no proxy config maintained | |
| You decide | Leave to planner | |

**User's choice:** Deploy-validated scale-up path.
**Notes:** Decision driven by user's SPOF reasoning. In-process litellm.Router is the POC runtime
(no self-operated SPOF; CF stays managed edge chokepoint); standalone proxy + provider-key isolation
deferred as prod-hardening/scale-up.

---

## Claude's Discretion

- `gateway_events` / `budget_ledger` table schema + migration placement.
- Exact `litellm.Router` load pattern from yaml; `langchain_litellm` binding.
- Pre-call token-cost estimation method.
- OTel exporter/config surface + multi-exporter fan-out shape.
- Deterministic GW-03 cross-provider cascade-failure trigger.

## Deferred Ideas

- Standalone LiteLLM proxy runtime + centralized budget + provider-key isolation → prod hardening / scale-up.
- `wrangler` publish/dry-run + idempotency → Phase 5 / DEP-02.
- Real eval harness (LLM-judge) → Phase 4 / SI-01.
- Live GCP infra provisioning → v2 (DEP-03/04).
- Data-residency enforcement → out of POC scope (model processing may leave AU).
