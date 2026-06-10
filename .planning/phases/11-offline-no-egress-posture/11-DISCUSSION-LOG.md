# Phase 11: Offline / No-Egress Posture - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-10
**Phase:** 11-offline-no-egress-posture
**Areas discussed:** Egress-assertion scope, Default-lane no-model-egress enforcement, OFFLINE posture expression, Assertion reach into the stack

---

## Scope clarification (load-bearing, raised before answering)

User corrected the framing of the whole phase: **"Offline scope only extends to not using
cloud hosted LLMs, not restricting every online service."** All four areas were re-presented
with assertions scoped to the **cloud-LLM / model-gateway egress path only** (deny-list of
cloud-LLM markers/hosts), explicitly NOT a blanket network/socket block. Local Postgres,
self-hosted Langfuse, in-stack service-DNS backends, and SaaS tool-pack adapters stay
legitimate. This reframing eliminated the `pytest-socket disable_socket` (block-all) option as
an over-reach.

---

## Egress-assertion scope (OFFLINE-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Whole-file sweep, all 4 profiles | Whole-file cloud-LLM-marker sweep over vllm/ollama + both compose-variant profiles; allowlist loopback + service-DNS, deny cloud-LLM markers anywhere | ✓ |
| api_base-only, add compose profiles | Keep api_base-only, extend to the 2 compose profiles | |
| Keep current (2 profiles, api_base) | Leave test_local_profiles.py as-is | |

**User's choice:** Whole-file sweep, all 4 profiles (recommended)
**Notes:** Catches a cloud-LLM ref outside `api_base`; service-DNS (`vllm:8000`/`ollama:11434`) treated as egress-free in-stack.

---

## Default-lane no-model-egress enforcement (OFFLINE-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Model-host deny-guard | Autouse test guard raising ONLY on cloud-LLM hosts (anthropic/vertex/CF/cloud MODEL_GATEWAY_BASE_URL); all else allowed; zero new dep | ✓ |
| Assert-by-construction | Monkeypatch the litellm/provider egress seam to raise-if-called, assert not called | |
| Both: guard + construction test | Ship both | |

**User's choice:** Model-host deny-guard (recommended)
**Notes:** Correctly scoped to the model path — NOT a global socket block (that over-reaches into Postgres/SaaS). Default creds-free lane makes no model call today, so it passes clean and proves the posture. Planner must add a non-vacuous test exercising a default-lane path under the fixture.

---

## OFFLINE posture expression (OFFLINE-01)

| Option | Description | Selected |
|--------|-------------|----------|
| .env.offline.example artifact | Concrete .env.offline.example zeroing cloud-LLM/gateway creds (CF/Anthropic/Vertex), local api_base, + RUNBOOK section; SaaS creds untouched | ✓ |
| Documented-posture only | RUNBOOK prose + existing blank keys; no new artifact | |

**User's choice:** .env.offline.example artifact (recommended)
**Notes:** Concrete + testable; no new runtime OFFLINE env-guard (zero-src forbids reading it).

---

## Assertion reach into the stack (OFFLINE-02 / roadmap "across the assembled local stack")

| Option | Description | Selected |
|--------|-------------|----------|
| Profiles + compose env | Also sweep docker-compose.yml api/worker env for cloud-LLM api_base / valued cloud-LLM keys; local refs stay legitimate | ✓ |
| Profiles only | Sweep only model_gateway.*.yaml profiles | |

**User's choice:** Profiles + compose env (recommended)
**Notes:** Honors the roadmap "assembled local stack" wording over the narrower "model profiles" reading.

---

## Claude's Discretion

- Exact connect/transport seam for the deny-guard (socket-level vs httpx/litellm transport hook) — mechanism open, decision = deny cloud-LLM hosts at connect level.
- Final cloud-LLM marker/host list (D-01/D-02 lists are the floor; keep cloud-LLM-scoped).

## Deferred Ideas

- Runtime OFFLINE enforcement guard (env-gated hard block) — needs a `src/` change; deferred past the zero-src milestone.
- Distinct-model-per-tier locally — already deferred in Phase 8.
- Blanket no-network test posture — explicitly rejected as out-of-scope over-reach.
