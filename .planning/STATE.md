---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: — Local / Offline Deployability
status: milestone_complete
stopped_at: Phase 11 complete — v1.1 (Local / Offline Deployability) milestone complete
last_updated: "2026-06-11T01:48:00.000Z"
last_activity: 2026-06-11 — Phase 11 complete (Offline / No-Egress Posture); v1.1 milestone complete
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 9
  completed_plans: 9
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** A long-running agent mesh takes a client request through ingress, durable orchestration, and a write-gated tool action — the write blocked until a human approves — and the whole run is observable and auditable.
**Current focus:** v1.1 milestone (Local / Offline Deployability) COMPLETE — Phase 11 (Offline / No-Egress Posture) done. Run `/gsd:complete-milestone` to archive v1.0 (phases 01–07 still in place) and reset the SDK frontmatter counters.

## Current Position

Phase: 11 (offline-no-egress-posture) — COMPLETE
Plan: 3 of 3 complete
Status: v1.1 milestone complete
Last activity: 2026-06-11 — Phase 11 complete (3/3 plans; verified 11/11 must-haves)

Progress: [██████████] 100% (4/4 v1.1 phases: 8, 9, 10, 11)

**Milestone v1.1 scope:** run the whole mesh fully local + offline — vLLM + Ollama behind LiteLLM (Phase 8), local Postgres(pgvector) + self-hosted Langfuse (Phase 9), full-stack docker-compose (Phase 10), offline no-egress posture (Phase 11). Config/compose/docs/tests ONLY — zero `src/` change; deployment names unchanged so agent + gateway code are untouched.

**v1.0 complete (2026-06-08):** Phases 1–7 done — durable Postgres core + authenticated/replay-proof approval gate; real LangGraph supervisor + Deep Agents roster + durable checkpointer + interrupt HITL; live LiteLLM gateway (budgets/cascades) + CF AI Gateway upstream + Langfuse; Tool Gateway framework + HubSpot/Google Workspace/Composio/Nango + 5 reference adapters + Xero; real held-out self-improvement loop + CycloneDX ML-BOM + non-hot promotion/rollback; full E2E proofs + idempotent deploy-script validation (SC-2/CR-01 gap closed via 07-05, 4/4 verified). Deploy-ready, not production-ready. v1.0 not yet archived via `/gsd:complete-milestone` (phase history 01–07 preserved in place).

## Performance Metrics

**Velocity:**

- Total plans completed: 25
- Average duration: — min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 02 | 3 | - | - |
| 06 | 6 | - | - |
| 07 | 5 | - | - |
| 08 | 2 | - | - |
| 10 | 3 | - | - |
| 11 | 3 | - | - |

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
- 09-01 (2026-06-10): local data+telemetry plane wired — best-effort `make run-pg` (single pgvector/pgvector:pg16, persistent -d + named volume, never CI), test-pg lane extended with the new test, `.env.example` pinned dev-only DATABASE_URL/TEST_DATABASE_URL (postgres:postgres@localhost:5432/agent_mesh) + LANGFUSE_HOST=http://localhost:3000 (keys blank), RUNBOOK "Local data & telemetry plane" section (Postgres run path + doc-only Langfuse self-host). D-03 reconciliation honored: conftest `_apply_migrations` already applied 0001->0004; only the stale docstring was fixed (tuple kept, no glob). New `tests/test_local_data_plane.py` asserts 0003 cols + 0004 tables + reachability via information_schema, loud-skips on unset TEST_DATABASE_URL. Zero src/ change; default lane 312 passed/10 skipped

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

Last session: --stopped-at
Stopped at: Phase 11 complete (3/3 plans; verified 11/11 must-haves; status: passed) — v1.1 milestone complete

**Phase 11 result (2026-06-11):** offline / no-egress posture is an ASSERTED property, zero `src/` change. **11-01** (D-01+D-04, OFFLINE-02) extended `tests/test_local_profiles.py` to a whole-file cloud-LLM marker sweep across all 4 local profiles (loopback + service-DNS allowlist) + new `tests/test_offline_compose_env.py` for the docker-compose api/worker env blocks; `config/model_gateway.cloud.yaml` is the negative control that TRIPS the sweep (non-vacuous). **11-02** (D-02, OFFLINE-03) new `tests/test_offline_deny_guard.py` — function-scoped autouse `socket.getaddrinfo` deny-guard raising only on cloud-LLM hosts (anthropic/Vertex `aiplatform.googleapis.com`/CF), passing through Postgres/Langfuse/service-DNS/SaaS; sync+async `anthropic/` positive controls assert on the guard's unique `OFFLINE deny` message (hardened from a wrong-reason `anthropic.com` match); creds-gated; `LITELLM_LOCAL_MODEL_COST_MAP=True`. **11-03** (D-03, OFFLINE-01) `.env.offline.example` (cloud-LLM/gateway creds blanked incl. `VERTEX_LOCATION`, SaaS creds normal) + RUNBOOK "Offline / no-egress posture" section + valued-key sweep `tests/test_offline_posture_env.py` + durable env-gated zero-`src/` invariant `tests/test_zero_src_invariant.py` (loud-skips unless `ZERO_SRC_BASE` set; [BLOCKING] enforcing run at base `5092323` passed non-vacuously, `git diff 5092323..HEAD -- src/` byte-empty). Full lane `make test -m "not live"` → 346 passed / 11 skipped. Verifier: 11/11 must-haves, status passed.

**Next:** v1.1 (Local / Offline Deployability, phases 8–11) is COMPLETE. Run `/gsd:complete-milestone` to archive v1.0 (phases 01–07 still in place) and reset the SDK frontmatter counters (the analyzer clobbers them otherwise — `phase.complete` had set an impossible 8/7/114% this run). Security gate: **CLOSED** — `11-SECURITY.md` SECURED, 13/13 threats closed, 0 open (ASVS L1; auditor re-ran the tests for non-vacuity incl. the armed `ZERO_SRC_BASE` run, commit d053179). Code review for Phase 11 was advisory and its reviewer returned truncated (no `11-REVIEW.md`); re-run `/gsd:code-review 11` if a written record is wanted — the highest-value bug class (assertion vacuity) was already caught + fixed in execution and re-confirmed by the security audit.

**Phase 10 result (2026-06-10):** one-command full-stack `docker-compose.yml` (api+worker+gui+pgvector postgres+migrate+Langfuse-v3-profile+vLLM/Ollama backends; no litellm container per D-06); shared command-parameterized `Dockerfile` (carries docker-cli for worker DooD) + `.dockerignore`; compose-variant model profiles with service-DNS api_base (Finding #1); `make compose-up/down` (best-effort, not in `make test`); RUNBOOK full-stack section with dev-only disclosures; `tests/test_compose_config.py` (the only CI-wired P10 artifact — static `docker compose config` validation, docker loud-skip). Code review found + fixed 2 real bring-up Criticals (api `/health`→`/healthz`, redis healthcheck NOAUTH) in `cd5de7a`. 318 tests green; zero `src/` change confirmed.

**Note (carried):** GSD subagents ARE installed at `~/.claude/agents/` (init's `agents_installed:false` is a path-mismatch false negative — gsd-executor/verifier/code-reviewer spawn fine; used live in Phase 8).

**Note (recurring SDK gotcha):** SDK state-writes (`phase.complete`, `state.record-session`) re-derive milestone progress from the ROADMAP v1.0 section (phases 1–7, never archived) and clobber frontmatter back to 7/7/100%. Body text is the source of truth (v1.1 = 3/4, 75% after Phase 10). Durable fix: run `/gsd:complete-milestone` to archive v1.0 so the analyzer sees v1.1's 4 phases (8–11). (Phase 10's `phase.complete` clobbered to status:milestone_complete/8/114% — manually reverted to executing/7/100 + body 3/4.)

**Planned Phase:** 11 (offline-no-egress-posture) — 3 plans — 2026-06-10T19:35:16.698Z
