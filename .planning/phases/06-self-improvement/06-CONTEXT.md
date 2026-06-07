# Phase 6: Self-Improvement - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 6 is **re-scoped** from a 2-plan stub-replacement into the **real self-improvement
LOOP** for the agent mesh, driven by a deep-research review of 2025–2026 self-evolving-agent
SOTA (see Canonical References → Research). It delivers, end-to-end and Option-C-safe:

1. **A real evaluation harness** (SI-01) replacing the `evaluate_proposal` stub — proposals
   scored on a **held-out task set distinct from any optimization signal**, via a Langfuse
   experiment run over a versioned dataset, with item-level + run-level no-regression gating.
2. **A log-driven reflective proposer + bounded improvement loop** (SI-03, new) — a GEPA-style
   **offline, separated meta-agent** that mines collected traces and emits **inert** prompt/
   workflow diffs, with a capped, re-validated iteration loop. It never applies or promotes.
3. **CycloneDX ML-BOM-on-promotion + controlled versioned non-hot promotion with rollback**
   (SI-02) — promotion emits an ML-BOM snapshot bound to the promoted version; the artifact is
   referenceable only via versioned, non-hot wiring read at next start/deploy; rollback re-points
   to `previous_version`.

**Hard invariants that survive this expansion (non-negotiable):**
- **Option C only.** Proposer + loop are inert: structured `SelfImprovementProposal` diffs,
  never applied, never auto-promoted. Promotion is the single human-gated, non-hot chokepoint.
- **No runtime mutation** of active instructions/permissions/routing. (CLAUDE.md §8 guardrail.)
- **Default suite stays creds-free.** Any LLM-judge / live-model scoring runs **only** in the
  `live` opt-in pytest lane (`make test-live`), double-gated by the `live_creds` fixture.

**Out of this phase (moved to a NEW milestone — "Self-Evolving Surfaces"):**
- Memory growth/compression + skill-library promotion as governed proposals (→ SI-04, v2).
- Multi-agent topology / routing-depth evolution as governed proposals (→ SI-05, v2).
  These are a *different evolve-surface* (not prompts/tools/routes), need new data models and
  new regression controls (memory-poisoning, co-evolutionary drift), and are not in v1.

**Milestone re-scope (decided this session):** pulling a live (inert) proposer + loop means this
work is a **governed self-evolving-agent build**, not the original "deploy-ready-only POC finish."
PROJECT.md milestone goal + creation of the "Self-Evolving Surfaces" milestone are surfaced as
explicit follow-up steps (see Deferred Ideas / Next Steps), not silently folded here.

</domain>

<decisions>
## Implementation Decisions

### Evaluation harness (SI-01 — "Full adopt-set")
- **D-01:** The real harness is a **Langfuse experiment runner** (Sept–Nov 2025 SDK:
  `experiments-via-sdk`) executing the candidate over every item in a **versioned held-out
  dataset**, recording **both item-level and run-level evaluators**. This replaces the boolean
  `evaluate_proposal` stub as the scoring engine.
- **D-02 (anti-reward-hack, central control):** Proposals are scored on a **held-out / realistic
  task set DISTINCT from any signal the proposer optimized against**. Never gate on the
  optimization signal. (Research: reward hacking is pervasive and *worsens* with iterations —
  73.8% Kernel-Bench / 46.8% ALE-Bench proxy-gain-without-real-gain; 26.4%→57.8% as steps 10→100.)
- **D-03 (no-regression gate):** Promotion-eligibility requires candidate **≥ baseline on
  aggregate gate metrics AND no item-level regression beyond a configured threshold**. Aggregate
  alone can mask item-level regressions ("a 4% avg improvement can hide a 16% regression") — so
  item-level drill-down is mandatory. Use Langfuse baseline-vs-candidate compare (green/red deltas).
- **D-04 (deterministic items):** Held-out eval items are **deterministic frozen-context
  snapshots** so candidate and baseline are scored on identical inputs (MIRAGE-Bench
  contextual-snapshot technique).
- **D-05 (LLM-judge — opt-in lane only):** Any LLM-judge scoring dimension runs **only** in the
  `live` pytest lane. It must apply **position-bias control (order-swap / order randomization)**
  — position bias is systematic and *worst when two candidates are close in quality*, which is
  exactly the SI gate case — and must **not be the sole arbiter for close-margin proposals**.
- **D-06 (judge calibration + statistical gate — pulled in):** The LLM-judge gate is **calibrated
  against a small human-labelled set** estimating judge TPR/FPR, and requires a **statistically
  valid below-threshold / no-regression test with finite-sample Type-I error control**
  (arXiv:2601.20913). Calibration set MUST match the promotion task distribution. This is
  `live`-lane / opt-in machinery; it does not run in the default creds-free suite.

### Improvement proposer + loop (SI-03 — new, pulled in)
- **D-07 (proposer = GEPA-style, offline, separated):** A **log-driven reflective proposer**
  samples collected execution traces (reasoning, tool calls, tool outputs), reflects in natural
  language to diagnose failures, and emits **prompt/workflow diffs only**. It is a **separated
  meta-agent (offline proposer + review pipeline)** — NOT wired inline into the live task
  supervisor. (Research design-pattern #2; GEPA is the production-viable mechanism, beats GRPO
  RL by ~6% avg / up to 20% with up to 35x fewer rollouts.) `reflect_on_task(...)` is the seam it
  produces into.
- **D-08 (inert):** The proposer mutates nothing live. It produces structured
  `SelfImprovementProposal` artifacts (existing contract). Nothing executes on creation.
- **D-09 (bounded loop):** The improvement loop **caps optimization iterations** and
  **re-validates on the held-out set each round**. The held-out set is protected from proposer
  visibility so it cannot (even indirectly) be optimized against. (Open question: exact iteration
  cap, held-out dataset size, alpha/threshold — left to research/planner; see Open Questions.)
- **D-10 (DGM out of scope):** No autonomous self-code-rewriting / autonomous benchmark-gated
  acceptance (Darwin Gödel Machine pattern). Acceptance is human-gated, non-hot — categorically
  different from DGM's autonomous gate.

### AI-BOM + promotion (SI-02 — "Adopt CycloneDX ML-BOM now")
- **D-11 (ML-BOM shape):** Promotion generates a **CycloneDX ML-BOM** snapshot (ECMA-424 v1.7,
  the open standard) from the deployment + tool-pack manifests, capturing
  **prompts / tools / models / model-routes / dataset version / eval results**, bound to the
  promoted version, retained for rollback + audit (12-month retention profile). Fills the existing
  `PromotionRecord.ai_bom_snapshot_id` link. (Note: criterion 2 only literally requires "a
  snapshot from the manifests"; full ECMA-424 conformance is adopted as the deliberate shape, but
  is an enhancement over the literal bar — keep conformance pragmatic for the POC.)
- **D-12 (non-hot wiring):** The promoted artifact is referenceable **only via versioned, non-hot
  wiring read at next start/deploy** — there is a loader seam that reads the active version at
  boot; promotion does NOT hot-swap running config. Proven by a test that a promotion does not
  change running config until an explicit reload/boot step.
- **D-13 (rollback):** `rollback_promotion(...)` re-points the active version pointer to
  `previous_version` (not merely a status flip), so the next-start loader reads the restored
  version. Proven by a test.

### Test lanes
- **D-14:** Default lane `make test` (`pytest -m "not live"`) stays fully **creds-free** — the
  deterministic harness, no-regression gates, ML-BOM generation, promotion/rollback wiring all run
  here. The `live` lane `make test-live` (`pytest -m live` + `live_creds` fixture, `pyproject.toml`
  marker) carries the LLM-judge + calibration + any real-model scoring. (Criterion 4 satisfied by
  construction — marking the judge path `live`.)

### Requirement edits (decided: "Edit REQUIREMENTS.md + CONTEXT.md")
- **D-15:** Rewrite SI-01/SI-02 in `.planning/REQUIREMENTS.md` and add sub-requirement IDs
  (SI-01a–d, SI-02a–b) + a new **SI-03** (proposer + loop), plus deferred **SI-04/SI-05**
  (memory/skill/topology) under v2 "Self-Evolving Surfaces (Milestone 2)". Update traceability +
  coverage. ROADMAP Phase 6 block updated to the loop scope. Done as confirmed edit steps this
  session.

### Claude's Discretion
- Exact iteration cap, held-out dataset size, calibration-set size, alpha / below-threshold
  failure-rate numbers (research establishes the *method*, not POC-specific numerics).
- Held-out dataset versioning/refresh/contamination-protection mechanism.
- Specific CycloneDX ML-BOM field mapping for LangGraph checkpoints / Deep Agents roster /
  Langfuse prompt+dataset versions; whether to also map to NIST AI RMF / ISO-42001 (only
  CycloneDX surfaced a confirmed primary-source claim).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Normative project docs
- `CLAUDE.md` §1, §4 (self-improvement risk row), §8 GSD guardrails — Option C, no runtime
  autonomous self-modification, bounded roster.
- `docs/self-improvement-loop.md` — the normative Option-C design: pipeline states, proposal
  types/risk floors, safety boundaries (§6), rollback (§7), AI-BOM implications (§8), and the
  explicit "What is NOT in this POC" (§9) list this phase is closing.
- `docs/production-readiness-caveats.md` — hardening boundaries that stay deferred.
- `.planning/REQUIREMENTS.md` — SI-01/SI-02 (+ SI-01a–d, SI-02a–b, SI-03) as edited this session.
- `.planning/ROADMAP.md` → Phase 6 block (updated to loop scope).

### Existing code seams (must read before changing)
- `src/agent_mesh/services/self_improvement.py` — `evaluate_proposal` (stub to replace, L149),
  `reflect_on_task` (proposer seam, L110), `open_promotion_approval` (L197, hash-rebind gate),
  `promote_proposal` (L235, refuses w/o passing eval + APPROVED hash-matching approval),
  `rollback_promotion` (L297).
- `src/agent_mesh/contracts/models.py` — `AIBOMSnapshot` (L213, generator missing),
  `PromotionRecord.ai_bom_snapshot_id` (L350, link to fill); `enums.py` `ProposalStatus`/
  `ProposalType`/`ProposalRiskLevel`.
- `src/agent_mesh/observability.py` — Phase-3 Langfuse dataset/eval seed to build the experiment
  runner on.
- `migrations/0002_self_improvement.sql` — durable proposals/evaluations/promotions store.
- `tests/conftest.py` (L115–126 `live_creds`), `pyproject.toml` (L92 `live` marker),
  `Makefile` (`test` / `test-live`) — the opt-in lane mechanism.
- `manifests/deployment.manifest.yaml`, `manifests/tool_pack_manifest.yaml` — ML-BOM sources.

### Research (deep-research report, 2026-06-07, 23 verified claims — primary sources)
- Surveys / taxonomy: arXiv:2507.21046, arXiv:2508.07407 (what/when/how to evolve; safety,
  scalability, co-evolution flagged as UNSOLVED → validates Option C).
- Proposer: arXiv:2507.19457 (GEPA — reflective prompt evolution > RL).
- Skeptical / out-of-scope: arXiv:2505.22954 (Darwin Gödel Machine; authors kept sandbox + human
  oversight); OpenReview id=ikrQWGgxYg + arXiv:2407.04549 (reward hacking pervasive & worsens).
- Eval harness: `langfuse.com/docs/evaluation/experiments/experiments-via-sdk` +
  changelogs 2025-09-17 (runner) / 2025-11-06 (baseline compare).
- LLM-judge: arXiv:2406.07791 (position bias systematic, worst at close margins);
  arXiv:2601.20913 + arXiv:2604.03257 (calibration TPR/FPR + finite-sample Type-I gate);
  arXiv:2507.21017 (MIRAGE-Bench frozen-context snapshot technique).
- Provenance: `cyclonedx.org/capabilities/mlbom/` (ML-BOM ECMA-424 v1.7, Oct 2025).
  (Misc: arXiv:2509.26354 "Your Agent May Misevolve" — emergent risk corroboration.)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `self_improvement.py`: full pipeline already exists (reflect→evaluate→approve→promote→rollback)
  with hash-rebind approval binding; Phase 6 swaps the `evaluate_proposal` body for the real
  harness, fleshes out `reflect_on_task` into the GEPA proposer seam, and fills the ML-BOM +
  non-hot-wiring gaps in `promote_proposal`/`rollback_promotion`.
- `observability.py`: Phase-3 Langfuse dataset/eval seed → base for the experiment runner.
- `AIBOMSnapshot` model + `PromotionRecord.ai_bom_snapshot_id` link already defined.
- `migrations/0002_self_improvement.sql`: durable store for proposals/evaluations/promotions.
- `live` marker + `live_creds` fixture: ready-made opt-in lane for judge/calibration.

### Established Patterns
- Payload-hash approval binding (tool-call gate) is reused for promotion approval — editing the
  patch after approval invalidates it (already tested).
- Tenant-scoping required on all repo reads (DUR-02) — eval/proposal/promotion queries included.
- Default-lane = creds-free; `live` = opt-in + creds-gated.

### Integration Points
- Eval harness ↔ Langfuse experiment runner + versioned dataset.
- Promotion ↔ CycloneDX ML-BOM generator ↔ deployment/tool-pack manifests.
- Non-hot wiring ↔ a boot/start version loader (new seam) read at next start/deploy.

</code_context>

<specifics>
## Specific Ideas

- "Determine the current most up-to-date approach … and adjust requirements to match" — the user
  commissioned the deep-research report and chose to **pull all four bucket-3 items in** (full
  ambition), then accept a **split** (Phase 6 = loop; memory/topology = new milestone) for
  controllability, and **re-scope the milestone** to a governed self-evolving build.
- User reasons via SPOF / controllability: rejected the single un-verifiable mega-phase in favour
  of separate verifiable boundaries.

</specifics>

<deferred>
## Deferred Ideas

### → New milestone "Self-Evolving Surfaces" (not v1)
- **SI-04:** Memory growth/compression + skill-library promotion through the same
  proposal→eval→ML-BOM→promotion gate, with memory-poisoning regression controls.
- **SI-05:** Multi-agent topology / routing-depth evolution as governed proposals, with
  co-evolutionary-drift controls.

### Explicit follow-up steps (surfaced, not silently done)
- **PROJECT.md milestone-goal rewrite** to "governed self-evolving-agent build" + creation of the
  "Self-Evolving Surfaces" milestone → recommend `/gsd:new-milestone` as the proper tool (memory/
  topology is a *future* milestone; it does not need to exist before Phase 6 plans).

### Beyond POC (stays deferred / out of scope)
- DGM-style autonomous self-code modification — permanently excluded by Option C.
- Full NIST AI RMF / ISO-42001 control mapping — only CycloneDX confirmed for the POC.

</deferred>

---

*Phase: 6-self-improvement*
*Context gathered: 2026-06-07*
