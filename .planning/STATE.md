---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: — Local / Offline Deployability
status: verifying
stopped_at: Completed 08-02-PLAN.md
last_updated: "2026-06-08T11:27:36.688Z"
last_activity: 2026-06-08
progress:
  total_phases: 7
  completed_phases: 7
  total_plans: 37
  completed_plans: 37
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** A long-running agent mesh takes a client request through ingress, durable orchestration, and a write-gated tool action — the write blocked until a human approves — and the whole run is observable and auditable.
**Current focus:** Phase 08 — local-inference-lane

## Current Position

Phase: 08 (local-inference-lane) — COMPLETE
Plan: 2 of 2 (both complete)
Status: Phase complete — ready for verification
Last activity: 2026-06-08

Progress: [██████████] 100%

**Milestone v1.1 scope:** run the whole mesh fully local + offline — vLLM + Ollama behind LiteLLM (Phase 8), local Postgres(pgvector) + self-hosted Langfuse (Phase 9), full-stack docker-compose (Phase 10), offline no-egress posture (Phase 11). Config/compose/docs/tests ONLY — zero `src/` change; deployment names unchanged so agent + gateway code are untouched.

**v1.0 complete (2026-06-08):** Phases 1–7 done — durable Postgres core + authenticated/replay-proof approval gate; real LangGraph supervisor + Deep Agents roster + durable checkpointer + interrupt HITL; live LiteLLM gateway (budgets/cascades) + CF AI Gateway upstream + Langfuse; Tool Gateway framework + HubSpot/Google Workspace/Composio/Nango + 5 reference adapters + Xero; real held-out self-improvement loop + CycloneDX ML-BOM + non-hot promotion/rollback; full E2E proofs + idempotent deploy-script validation (SC-2/CR-01 gap closed via 07-05, 4/4 verified). Deploy-ready, not production-ready. v1.0 not yet archived via `/gsd:complete-milestone` (phase history 01–07 preserved in place).

## Performance Metrics

**Velocity:**

- Total plans completed: 17
- Average duration: — min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 02 | 3 | - | - |
| 06 | 6 | - | - |
| 07 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 05 P07 | 15 | 2 tasks | 4 files |
| Phase 06 P01 | 31min | 3 tasks | 6 files |
| Phase 08 P02 | 12 | 3 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Init: Full-vertical milestone scope — complete all stubs to local-validated
- Init: Deploy-ready only — no live GCP provisioning this milestone
- Init: Fix the critical `/v1/approvals` auth bypass this milestone (Phase 1)
- Init: Coarse granularity, standard (horizontal-layer) phasing, quality model profile
- 05-07: Xero rides existing composio adapter (no new module); BEEHIIV_LIVE_PUBLICATION_ID excluded via _NON_ENV (non-credential toggle) to keep credential-docs floor at 12
- 06-01: active-version pointer is a dedicated 0004 row (self_improvement_active_version), not derived from PromotionRecord — read+write both in repository.py
- 06-01: cyclonedx-python-lib 11.8.0 confirmed; V1_7 output API via cyclonedx.output.make_outputter + cyclonedx.schema SchemaVersion.V1_7/OutputFormat.JSON (resolves RESEARCH A2 for 06-05)
- v1.1 (2026-06-08): Local/Offline Deployability milestone — config/compose/docs/tests ONLY, zero src/ change. vLLM + Ollama slot behind the existing LiteLLM Router seam keyed on stable deployment names (low/medium/high-complexity), so agent + gateway code are untouched. Offline enforcement is test-asserted over config, not a runtime guard. vLLM was the originating slice (user request) folded into a 4-phase milestone (8–11).
- 08-01 (2026-06-08): local profiles author egress-free headers self-authored (NOT copied from cloud file — case-sensitive negative greps would pass a copied header yet still leak cloud markers); value lines unquoted so literal-substring grep gates match; vLLM api_base ends /v1 (hosted_vllm appends only chat/completions, Pitfall 1), Ollama ollama_chat/ + :11434 no /v1
- v1.1 (2026-06-08): skipped `phases.clear` during new-milestone (would have deleted unarchived v1.0 phase dirs 01–07); phases continue at 08 so no collision. Run `/gsd:complete-milestone` to archive v1.0 cleanly when ready.
- 08-02 (2026-06-08): local lane tooling complete — five Makefile targets (cp-swap use-*, best-effort run-* kept out of CI per D-07), LOCAL-04 guard (loopback api_base + no cloud markers, offline build_router, inverted vs test_d06_chokepoint), RUNBOOK Local inference lane section; canonical test interpreter is .venv/bin/python (litellm 1.83.7), bare PATH python 3.14 lacks deps (pre-existing env note)

### Pending Todos

None yet.

### Blockers/Concerns

- Critical (carried into Phase 1): `/v1/approvals` accepts a self-asserted `approver_id` with no signature (CONCERNS.md #1) — closed by SEC-01.
- GSD subagents not installed (`agents_installed: false`); roadmap was generated inline. Phase research/plan-check/verifier are enabled in config but require `npx get-shit-done-cc@latest --global` to spawn.

## Deferred Items

Items acknowledged and carried forward:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Deploy | Live GCP provisioning + FinOps review (DEP-03, DEP-04) | Deferred to v2 | Init |
| Self-improvement | SI-04 (memory/skill-library evolution) + SI-05 (multi-agent topology/routing-depth evolution) | Deferred to new **"Self-Evolving Surfaces"** milestone (create via `/gsd:new-milestone`) | Phase 06 discuss (2026-06-07) |
| Tools | TOOL-03 (reference adapters) + TOOL-04 (aggregators) | **Promoted v2→v1 2026-06-06** — TOOL-04 + flagship adapters in Phase 4; TOOL-03 in Phase 5 | Re-scoped Phase 04 |
| Hardening | Immutable ledger, egress controls, kill switches, signed images, GDPR deletion, HA | Production hardening (caveats) | Init |
| Observability | OBS-01 tool-event spans — wire OTel spans on tool calls | **Scheduled for Phase 04** (D-10, framework emits them once a real adapter exists) | Phase 03 (03-VERIFICATION Gap 2) |
| Model gateway | `gemini-1.5-flash` (low-complexity route) unmapped in this litellm build's price map — pre-call cost estimate raises; within-budget real-`_delegate` 4-node run falls back to stub lane in one negative-control test | Minor env pricing gap; revisit in Phase 04/05 tool+model-route work | Phase 03 (03-04 SUMMARY) |

## Session Continuity

Last session: 2026-06-08T11:27:24.561Z
Stopped at: Completed 08-02-PLAN.md

**Next:** Execute Plan 08-02 — consumers: Makefile run/swap targets (run-vllm/run-ollama, use-vllm/use-ollama/use-cloud), LOCAL-04 config-validation test (build_router over each local profile, no network), RUNBOOK local-inference section. LOCAL-03/04.

**Note (carried):** GSD subagents not installed (`agents_installed: false`) — executor/verifier/roadmapper run inline. Install via `npx get-shit-done-cc@latest --global` to enable spawned agents.

**Planned Phase:** 08 (local-inference-lane) — 2 plans — 2026-06-08T10:51:17.256Z
