# Phase 6: Self-Improvement - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-07
**Phase:** 6-self-improvement
**Areas discussed:** Eval harness depth + scoring, AI-BOM snapshot generation, Non-hot promotion
wiring, Rollback depth + reflection scope — then reframed by a `/deep-research` review of
2025–2026 self-evolving-agent SOTA into: SI-01 adopt-set, AI-BOM depth, bucket-3 pull-ins,
requirement-edit location, roadmap structure, milestone re-scope.

---

## Trigger: deep-research review

The user invoked `/deep-research` on "current most up-to-date approach for agent self-improvement
… adjust requirements to match." A 105-agent workflow returned 23 verified primary-source claims
(arXiv surveys 2507.21046 / 2508.07407; GEPA 2507.19457; DGM 2505.22954; reward-hacking
OpenReview ikrQWGgxYg / 2407.04549; Langfuse experiment-runner docs; position-bias 2406.07791;
calibration 2601.20913; CycloneDX ML-BOM). The advisor then framed the reshape as a
scope-discrimination problem (three buckets: sharpen SI-01, sharpen SI-02, defer the rest).

---

## SI-01 real eval harness — adopt-set

| Option | Description | Selected |
|--------|-------------|----------|
| Full adopt-set | Langfuse experiment runner + versioned held-out frozen-context dataset distinct from optimization signal; item+run no-regression vs baseline; LLM-judge order-swap in `live` lane only | ✓ |
| Lean deterministic-only | Deterministic held-out no-regression only; no LLM-judge lane | |
| You decide details | Lock principles, planner picks specifics | |

**User's choice:** Full adopt-set.
**Notes:** User first asked how the opt-in lane is determined — answered: existing pytest `live`
marker (`make test-live`) + `live_creds` fixture, double-gated; default `make test` excludes it.

## SI-02 AI-BOM snapshot — CycloneDX depth

| Option | Description | Selected |
|--------|-------------|----------|
| Adopt CycloneDX ML-BOM now | ECMA-424 v1.7 snapshot bound to promoted version | ✓ |
| Minimal now, CycloneDX as target | Minimal manifest snapshot; standard deferred to v2 | |
| You decide | Lock principle, planner picks shape | |

**User's choice:** Adopt CycloneDX ML-BOM now.

## Bucket-3 — pull into Phase 6 or defer?

| Option | Description | Selected (= pull in) |
|--------|-------------|----------|
| GEPA proposer / reflection subagent | Live log-driven reflective proposer | ✓ |
| Judge calibration + Type-I certification | TPR/FPR calibration + finite-sample below-threshold gate | ✓ |
| Iteration cap + re-validate loop | Capped optimization loop, held-out re-validation each round | ✓ |
| Memory/skill/topology evolution | Extend evolve-surface beyond prompts/tools/routes | ✓ |

**User's choice:** ALL FOUR pulled in.
**Notes:** Maximal ambition (consistent with user's known decision style). Claude flagged this
converts a 2-plan POC phase into a full self-evolving build and surfaced consequences in
controllability/SPOF terms before writing anything — did not silently accept.

## Where requirement adjustments land

| Option | Description | Selected |
|--------|-------------|----------|
| Edit REQUIREMENTS.md + CONTEXT.md | Rewrite SI-01/SI-02, add sub-IDs | ✓ |
| CONTEXT.md only | Leave REQUIREMENTS.md unchanged | |
| Rewrite SI-01/SI-02 only | No new sub-IDs | |

**User's choice:** Edit REQUIREMENTS.md + CONTEXT.md.

## Roadmap structure (how to hold the expanded scope)

| Option | Description | Selected |
|--------|-------------|----------|
| Split: P6 loop + new milestone | P6 = real SI loop; memory/topology → new milestone | ✓ |
| Single mega Phase 6 | All 4 buckets in one un-verifiable phase | |
| Three phases this milestone | P6 SI-01/02; new P7 proposer; new P8 memory; grow 7→10 | |

**User's choice:** Split — P6 loop + new milestone.
**Notes:** User reasons via SPOF/controllability — rejected the single mega-phase for separate
verifiable boundaries.

## Milestone goal re-scope

| Option | Description | Selected |
|--------|-------------|----------|
| Re-scope to self-evolving build | Milestone becomes a governed self-evolving-agent build | ✓ |
| Keep POC milestone tight | Stay deploy-ready-only; defer proposer/loop/memory to future | |
| Proceed, decide milestone later | Lock P6 scope now, defer PROJECT.md rewrite | |

**User's choice:** Re-scope to self-evolving build.

---

## Claude's Discretion

- Exact iteration cap, held-out dataset size, calibration-set size, alpha / below-threshold
  failure-rate numerics (research gives method, not POC numbers).
- Held-out dataset versioning / contamination-protection mechanism.
- CycloneDX ML-BOM field mapping for LangGraph checkpoints / Deep Agents roster / Langfuse
  prompt+dataset versions; whether to also map NIST AI RMF / ISO-42001.

## Deferred Ideas

- **SI-04 / SI-05** (new "Self-Evolving Surfaces" milestone): memory growth/compression +
  skill-library promotion; multi-agent topology/routing-depth evolution — through the same
  proposal→eval→ML-BOM→promotion gate, with memory-poisoning + co-evolutionary-drift controls.
- **PROJECT.md milestone-goal rewrite + new-milestone creation** → `/gsd:new-milestone` follow-up.
- DGM-style autonomous self-code modification — permanently excluded by Option C.
