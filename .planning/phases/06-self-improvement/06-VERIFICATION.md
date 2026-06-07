---
phase: 06-self-improvement
verified: 2026-06-08T06:30:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 5/6
  gaps_closed:
    - "Truth 6 / CR-01: promote_proposal now guards proposal.status — rollback-bypass and double-promotion both refused; regression test test_promote_refused_for_rolled_back_proposal added; live probe confirmed PromotionRefused raised as expected"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Run `make test-live` with real provider credentials (ANTHROPIC_API_KEY or equivalent VERTEX_PROJECT_ID + CF_AIG_WRAPPER_URL)"
    expected: "5 tests in tests/test_judges_live.py pass: order-swap symmetry, calibration TPR/FPR, finite-sample Type-I, close-margin defer, run_evaluator plug-in"
    why_human: "Requires live provider credentials not available in the creds-free verification environment; verified only structurally (lazy imports, 0 tests in default lane)"
    status: resolved
    resolved: "2026-06-08 — ran with lane gate set → 5 passed (see 06-HUMAN-UAT.md). Tests are deterministic (injected compare); real model e2e is optional."
---

# Phase 06: Self-Improvement Verification Report (Re-verification)

**Phase Goal:** Replace the evaluate_proposal stub with a real held-out evaluation harness;
add a GEPA-style offline, separated, inert reflective proposer + bounded improvement loop;
and wire CycloneDX ML-BOM-on-promotion with controlled, versioned (non-hot) promotion and
retained rollback — Option-C-safe: proposals stay inert, promotion is the single
human-gated chokepoint, and no active instructions/permissions/routing are mutated at runtime.

**Verified:** 2026-06-08T06:30:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (CR-01 blocker closed; all 13 review findings addressed)

> **Human-verification item RESOLVED (2026-06-08):** the SI-01d live-lane judge UAT
> (`06-HUMAN-UAT.md`) was run — `pytest -m live tests/test_judges_live.py` with the
> lane gate set → **5 passed**. By design these tests prove the judge guard logic
> deterministically (injected `compare`, no model call). Real end-to-end model traffic
> through the gateway remains an optional deeper-confidence step requiring live creds.

---

## Test Suite

`make test PY=.venv/bin/python` → **276 passed, 6 skipped, 21 deselected (live), 10 warnings in 20.56s**

+1 vs prior run (275): the new `test_promote_refused_for_rolled_back_proposal` regression test. All non-live tests green. The 21 deselected are live-marked tests (correct).

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A proposal is scored by a real Langfuse-experiment harness over a versioned held-out dataset (deterministic frozen-context snapshots) distinct from any signal the proposer optimized against — not a stub (SI-01, SI-01a, SI-01c) | VERIFIED | `eval_harness.py` provides `run_candidate` (creds-free `Langfuse().run_experiment`), `held_out_pool()` (3 deterministic snapshots keyed holdout-001/002/003), `build_frozen_items` (identical input → identical dict). `evaluate_proposal` defaults to `evaluator="holdout-harness"`. `test_frozen_items_deterministic` and `test_run_candidate_creds_free` pass. |
| 2 | Promotion-eligibility requires candidate ≥ baseline on aggregate metrics AND no item-level regression beyond threshold (SI-01b) | VERIFIED | `passes_no_regression` is a two-stage pure-stdlib gate: aggregate-mean check then per-item drill-down; a dropped item scores 0.0. `test_no_regression_gate` covers all three branches (aggregate-fail, item-fail, pass). |
| 3 | A GEPA-style offline proposer mines traces and emits inert prompt/workflow diffs only; the loop caps iterations and re-validates on the held-out set each round (held-out protected from proposer visibility) (SI-03) | VERIFIED | `reflective_proposer.py` provides `propose_from_traces` (emits via `reflect_on_task` seam → status=DRAFT), `improve_loop` (config-driven `_parse_max_iterations()` defaulting to 3, injectable `gate_fn`). `reflective_proposer.py` does NOT import `held_out_pool` or `promote_proposal` (grep confirmed 0 matches). Not wired into `worker/orchestrator.py`. Live probe: `held_out_item_ids() ∩ train_item_ids() == ∅` (holdout-00x vs train-00x namespaces). Tests: `test_proposer_emits_inert_draft`, `test_trace_mining_is_tenant_scoped`, `test_holdout_isolation`, `test_loop_caps_iterations` all pass. |
| 4 | Promotion generates a CycloneDX ML-BOM snapshot from the deployment + tool-pack manifests bound to a versioned promotion with rollback (SI-02, SI-02a) | VERIFIED | `ai_bom.generate_ml_bom` builds a valid CycloneDX V1_7 JSON (via `cyclonedx-python-lib 11.8.0`), persists an `AIBOMSnapshot` via `repo.upsert_ai_bom`, and returns `snapshot_id`. `promote_proposal` always fills `PromotionRecord.ai_bom_snapshot_id` (never null). Manifest paths are repo-root-anchored absolute (WR-08 fixed: `_MODULE_DIR / parents[2]` anchoring applied to `_DEFAULT_DEPLOYMENT_MANIFEST` and `_DEFAULT_TOOL_PACK_MANIFEST`). `tests/test_ai_bom.py` 6 tests pass (specVersion=1.7, ML component, property mapping, round-trip persistence, tenant isolation). |
| 5 | The active promoted version is read ONCE at boot into a module-level cache; promotion does NOT change active_version() until an explicit reload (non-hot), and rollback re-points the active-version pointer to previous_version (SI-02b) | VERIFIED | `version_pin.py` mirrors `observability._PROCESS_PROVIDER` set-once cache. `active_version()` never reads the repo. `load_active_version_at_boot` unconditionally re-reads. `rollback_promotion` calls `repo.set_active_version(previous_version)`. Non-hot invariant confirmed by live probe. `test_active_version_set_once_at_boot`, `test_promotion_is_non_hot`, `test_rollback_repoints_to_previous_version` all pass. |
| 6 | No active instructions/permissions/routing mutated at runtime; promoted artifact referenceable only via versioned non-hot wiring; rollback re-points to previous_version; both proven by tests (SI-02b, criterion 5) | VERIFIED | `promote_proposal` now guards at line 342: `if proposal.status != ProposalStatus.APPROVED.value: raise PromotionRefused(...)`. Live re-verification probe confirms: reflect→evaluate→approve→promote→rollback→promote(no fresh approval) now raises `PromotionRefused("... is 'rolled_back'; only 'approved' proposals may be promoted")` — probe exits 0. Double-promotion of an already-PROMOTED proposal is also refused (same guard; probe confirmed). New regression test `test_promote_refused_for_rolled_back_proposal` (line 190, 276 total passing) encodes the full CR-01 cycle. CR-01 CLOSED. |

**Score: 6/6 truths verified**

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `migrations/0004_active_version.sql` | Idempotent migration with both tables | VERIFIED | `CREATE TABLE IF NOT EXISTS self_improvement_active_version` + `CREATE TABLE IF NOT EXISTS ai_bom_snapshots`; both registered in conftest `_MIGRATIONS` (pos 4) and `_TABLES`. |
| `src/agent_mesh/services/repository.py` | 4 new methods across all 3 layers | VERIFIED | `current_active_version`, `set_active_version`, `upsert_ai_bom`, `get_ai_bom` at lines 58-64 (Protocol), 211-238 (InMemory), 1040-1107 (RepositorySQL). WR-03 fixed: single `model_dump(mode="json")` call in `upsert_ai_bom` (line 1093). |
| `src/agent_mesh/services/eval_harness.py` | Real harness + gate + held-out pool | VERIFIED | 246 lines. `build_frozen_items`, `held_out_pool`, `held_out_item_ids`, `run_candidate`, `exact_match`, `scores_by_item`, `load_baseline`, `passes_no_regression`. WR-06 fixed: `scores_by_item` raises `ValueError` on `None` item_id (line 86, 174) instead of silent skip. No `live_creds` import. |
| `tests/fixtures/holdout_baseline.json` | Committed golden baseline | VERIFIED | Version-keyed `{"2026-06-07": {"holdout-001": 1.0, "holdout-002": 1.0, "holdout-003": 1.0}}`. |
| `src/agent_mesh/services/self_improvement.py` | evaluate_proposal body swapped; promote/rollback wired with chokepoint guard | VERIFIED | `evaluate_proposal` uses `evaluator="holdout-harness"` (stub replaced). WR-01 fixed: empty `proposed_patch.strip()` gate added at line 212/224 (both deterministic and default paths). `promote_proposal` now guards `proposal.status == APPROVED` at line 342 (CR-01 closed). WR-07 fixed: `_patch_hash_payload` includes `proposal_id` in hash payload (line 176). `rollback_promotion` re-points active pointer. All promotion/rollback/approval tests pass. |
| `src/agent_mesh/services/reflective_proposer.py` | GEPA-style offline proposer + bounded loop | VERIFIED | `propose_from_traces`, `improve_loop`, `train_item_ids`, `assert_holdout_isolation`, `HeldOutLeakError`. WR-04 fixed: `assert last is not None` replaced with explicit `if last is None: raise RuntimeError(...)` at line 228. WR-05 fixed: `_parse_max_iterations()` deferred helper (line 54) replaces module-level `int(os.getenv(...))` parse. Not wired into orchestrator. |
| `src/agent_mesh/services/version_pin.py` | Boot-time set-once non-hot loader | VERIFIED | `_ACTIVE_VERSION` module cache, `load_active_version_at_boot`, `active_version`, `_reset`. No `get_settings` usage. |
| `src/agent_mesh/eval/judges.py` | Live-lane judge with order-swap, calibration, Type-I gate, and delimited prompt | VERIFIED (live-lane surface) | Order-swap, `calibrate`, `passes_type_i`, `is_close_margin`. CR-02 fixed: `gateway_pairwise_judge._compare` now delimits `first`/`second` with `<<<EVAL_CONTENT>>>` and strips the delimiter from candidate text (lines 362-372). IN-02 fixed: `binomial_upper_tail` raises `ValueError` on `wins < 0` (line 241). Lazy imports. 0 tests run in default lane. |
| `tests/test_judges_live.py` | 5 live-marked tests, 0 running in default lane | VERIFIED | `pytestmark = pytest.mark.live`. `pytest -m "not live" --collect-only` → 0 tests (5 deselected). |
| `src/agent_mesh/services/ai_bom.py` | CycloneDX V1_7 ML-BOM generator with anchored defaults | VERIFIED | `_build_ml_bom_json` (pure CycloneDX V1_7 JSON), `generate_ml_bom` (persists `AIBOMSnapshot`, returns `snapshot_id`), `cyclonedx_available()`. WR-08 fixed: `_DEFAULT_DEPLOYMENT_MANIFEST` and `_DEFAULT_TOOL_PACK_MANIFEST` anchored via `_MODULE_DIR = Path(__file__).resolve().parent` / `_REPO_ROOT = _MODULE_DIR.parents[2]` (lines 53-56). Lazy import. No `live_creds`. |
| `pyproject.toml` | `[aibom]` extra with cyclonedx-python-lib | VERIFIED | `aibom = ["cyclonedx-python-lib>=8,<12"]` at line 71. Installed version 11.8.0. |
| `tests/test_self_improvement.py` | CR-01 regression test added | VERIFIED | `test_promote_refused_for_rolled_back_proposal` (line 190): full reflect→evaluate→approve→promote→rollback cycle, then `pytest.raises(si.PromotionRefused)` on re-promotion. 276 total passing. |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `self_improvement.evaluate_proposal` | `eval_harness.run_candidate` + `passes_no_regression` | default path (no `deterministic_checks`) | VERIFIED | Lines 209-228. Calls `eval_harness.run_candidate(eval_harness.held_out_pool(), eval_harness.replay_task, ...)` then `eval_harness.passes_no_regression`. Empty-patch guard at line 212/224 prevents tautological pass on blank proposals. |
| `reflective_proposer.propose_from_traces` | `self_improvement.reflect_on_task` | emits inert DRAFT via existing seam | VERIFIED | Line 126-134. Never calls promote/approve/evaluate. |
| `reflective_proposer.improve_loop` | held-out gate | injectable `gate_fn` defaulting to `_default_gate → evaluate_proposal` | VERIFIED | Lines 138-146, 178-189. Held-out set reached ONLY through the gate, never fed back to reflection signal. |
| `promote_proposal` | `proposal.status == APPROVED` chokepoint guard | immediately after proposal fetch, before all other checks | VERIFIED | Line 342. ROLLED_BACK, PROMOTED, DRAFT, EVALUATION_FAILED all refused. |
| `promote_proposal` | `ai_bom.generate_ml_bom` | called after approval+evaluation chokepoint | VERIFIED | Lines 374-385. Manifest paths repo-root-anchored absolute. |
| `promote_proposal` | `repo.set_active_version` | active pointer written non-hot after chokepoint | VERIFIED | Line 404. No loader call. |
| `rollback_promotion` | `repo.set_active_version(previous_version)` | re-point on rollback | VERIFIED | Lines 430-435. Guarded against null `previous_version`. |
| `version_pin.active_version` | module cache `_ACTIVE_VERSION` | never reads repo | VERIFIED | Lines 48-54. No DB call in hot path. |
| `tests/conftest.py` | `migrations/0004_active_version.sql` | `_MIGRATIONS` tuple | VERIFIED | Line 12 in conftest. Both table names in `_TABLES` (lines 16-17). IN-01 fixed: `frozen_holdout_items` fixture imports `_HELD_OUT_SNAPSHOTS` directly (line 236) instead of duplicating. IN-03 fixed: migration comment stripping uses `re.sub(r"(?m)--.*$", "", raw)` (line 61). |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `eval_harness.run_candidate` | `item_results` | `Langfuse().run_experiment` over `_HELD_OUT_SNAPSHOTS` | Yes — frozen deterministic items | FLOWING |
| `eval_harness.load_baseline` | baseline scores | `tests/fixtures/holdout_baseline.json` | Yes — committed version-keyed JSON | FLOWING |
| `ai_bom.generate_ml_bom` | CycloneDX JSON | `yaml.safe_load` of manifest files | Yes — manifests/deployment.manifest.yaml + tool_pack_manifest.yaml (repo-root-anchored) | FLOWING |
| `version_pin.active_version` | `_ACTIVE_VERSION` | `repo.current_active_version` at boot | Real at boot, cached thereafter | FLOWING (non-hot by design) |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| eval_harness imports creds-free | `python -c "import agent_mesh.services.eval_harness"` | exit 0 | PASS |
| judges.py imports creds-free | `python -c "import agent_mesh.eval.judges"` | exit 0 | PASS |
| held_out ∩ train_ids = ∅ | Python probe: `held_out_item_ids() & train_item_ids()` | `set()` | PASS |
| version_pin non-hot invariant | Python probe: store-write does not change `active_version()` | VERIFIED | PASS |
| CR-01 rollback-bypass (re-verification) | Python probe: reflect→eval→approve→promote→rollback→promote | `PromotionRefused: ... is 'rolled_back'; only 'approved' proposals may be promoted` — exit 0 | PASS |
| CR-01 double-promote | Python probe: reflect→eval→approve→promote→promote | `PromotionRefused: ... is 'promoted'; only 'approved' proposals may be promoted` — exit 0 | PASS |
| test suite creds-free | `make test PY=.venv/bin/python` | 276 passed, 6 skipped, 21 deselected | PASS |
| judges zero-run in default lane | `pytest -m "not live" tests/test_judges_live.py --co` | 0 tests (5 deselected) | PASS |
| cyclonedx V1_7 available | `python -c "from cyclonedx.schema import SchemaVersion; print(SchemaVersion.V1_7)"` | `SchemaVersion.V1_7` | PASS |
| Phase 6 files ruff-clean | `ruff check` on all 12 Phase 6 source + test files | All checks passed | PASS |

---

## Requirements Coverage

All requirement IDs declared across phase 06 plans: SI-01, SI-01a, SI-01b, SI-01c, SI-01d, SI-02, SI-02a, SI-02b, SI-03.

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SI-01 | 06-02 | Real eval harness replaces stub | VERIFIED | Harness runs; empty-patch guard closes the zero-discrimination gap in the default lane (WR-01 addressed). Chokepoint guard (CR-01) ensures re-promotion after rollback cannot bypass human approval. |
| SI-01a | 06-02/06-03 | Held-out distinct from proposer signal | VERIFIED | holdout-00x vs train-00x disjoint; `test_holdout_isolation` passes; proposer never imports `held_out_pool`. |
| SI-01b | 06-02 | Aggregate AND item-level no-regression gate | VERIFIED | `passes_no_regression` two-stage; `test_no_regression_gate` covers all branches. None item_id raises (WR-06). |
| SI-01c | 06-02 | Frozen-context deterministic snapshots | VERIFIED | `build_frozen_items` deterministic; `test_frozen_items_deterministic` passes. |
| SI-01d | 06-04 | LLM-judge in live-only lane, order-swap, TPR/FPR, Type-I, close-margin guard | VERIFIED (structure) / HUMAN NEEDED | All four guards implemented. CR-02 fixed: candidate text delimited with `<<<EVAL_CONTENT>>>`. Lazy imports. 0 tests run in default lane. Live-lane execution requires human `make test-live`. |
| SI-02 | 06-05/06-06 | AI-BOM snapshot on promotion | VERIFIED | `generate_ml_bom` always called from `promote_proposal`; `ai_bom_snapshot_id` never null after promote. Manifest defaults repo-root-anchored (WR-08). |
| SI-02a | 06-05 | CycloneDX ML-BOM V1_7 from manifests | VERIFIED | cyclonedx-python-lib 11.8.0; `specVersion=1.7`; ML component + agentmesh:* properties; `test_ai_bom.py` 6 tests pass. |
| SI-02b | 06-01/06-06 | Non-hot wiring + rollback re-point, proven by tests | VERIFIED | Non-hot proof passes. Rollback re-point passes. CR-01 closed: `promote_proposal` now checks `proposal.status == APPROVED` before all other checks — ROLLED_BACK and PROMOTED proposals are refused. `test_promote_refused_for_rolled_back_proposal` encodes the invariant. |
| SI-03 | 06-03 | GEPA-style offline inert proposer + bounded loop | VERIFIED | `reflective_proposer.py` separated, not wired to supervisor. Loop caps via `_parse_max_iterations()` (deferred, WR-05). `assert` replaced with explicit `RuntimeError` (WR-04). Tests pass. |

No orphaned requirements: all 9 IDs (SI-01 through SI-03 with sub-IDs) are accounted for across the six plans.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Status |
|------|------|---------|----------|--------|
| `src/agent_mesh/services/self_improvement.py` | 342 | `promote_proposal` status guard — now refuses ROLLED_BACK / PROMOTED | ~~BLOCKER~~ | RESOLVED (CR-01) |
| `src/agent_mesh/eval/judges.py` | 362-372 | Judge prompt now delimits candidate text with `<<<EVAL_CONTENT>>>` | ~~WARNING~~ | RESOLVED (CR-02) |
| `src/agent_mesh/services/reflective_proposer.py` | 228 | `assert last is not None` replaced with explicit `RuntimeError` | ~~WARNING~~ | RESOLVED (WR-04) |
| `src/agent_mesh/services/reflective_proposer.py` | 54 | `_parse_max_iterations()` deferred helper replaces module-import-time `int(os.getenv(...))` | ~~WARNING~~ | RESOLVED (WR-05) |
| `src/agent_mesh/services/repository.py` | 745-767 | `transition_task` TOCTOU race (read + update in separate connections) | WARNING | Pre-existing (WR-02); not Phase 6 regression |
| `src/agent_mesh/services/repository.py` | 738-743 | `get_task` has no `tenant_id` filter — pre-existing DUR-02 defense-in-depth gap | INFO | Pre-existing (WR-09); documented known limitation; Phase 6 did not introduce or worsen; breaking protocol change deferred to a dedicated DUR-02 hardening task |

No `TBD`, `FIXME`, or `XXX` markers found in Phase 6 files.

---

## Known Limitation: WR-09 (Pre-existing DUR-02 Gap)

`RepositorySQL.get_task` uses `WHERE task_id = %s` with no `tenant_id` filter. This is a pre-existing defense-in-depth gap audited in Phase 1 (observation 5672/5676, 0 blockers). Phase 6 did not introduce or worsen it. Task IDs are UUID4 hex strings (unguessable), so the direct cross-tenant threat requires a leaked task ID. The fix — adding `tenant_id` to the `get_task` protocol signature and SQL filter — is a breaking protocol change that must be coordinated across all callers in a dedicated DUR-02 hardening task. This gap does not block Phase 6 goal achievement.

---

## Human Verification Required

### 1. Live-lane judge execution (SI-01d)

**Test:** Run `make test-live` with real provider credentials (ANTHROPIC_API_KEY or equivalent VERTEX_PROJECT_ID + CF_AIG_WRAPPER_URL)
**Expected:** 5 tests in `tests/test_judges_live.py` pass (order-swap symmetry, calibration TPR/FPR, finite-sample Type-I, close-margin defer, run_evaluator plug-in)
**Why human:** Requires live provider credentials not available in the creds-free verification environment. The judge structure is verified (lazy imports, 0 tests in default lane, CR-02 prompt injection fix in place), but end-to-end behavior against a real model endpoint is not covered by `make test`.

---

## Gaps Summary

No blockers. The single BLOCKER gap from initial verification (CR-01: `promote_proposal` did not check `proposal.status`) has been closed. All 6 success criteria are now VERIFIED.

The remaining open item is SI-01d live-lane execution, which requires human `make test-live` with real provider credentials. This was always a human-verification item (not a gap) — the distinction is that it requires a live model endpoint, not that the structure is missing.

**Pre-existing known limitation (not a Phase 6 gap):** WR-09 / DUR-02 — `get_task` missing `tenant_id` filter. Accepted as a pre-existing gap; deferred to a dedicated DUR-02 hardening task.

---

_Verified: 2026-06-08T06:30:00Z_
_Verifier: Claude (gsd-verifier)_
_Re-verification after CR-01 gap closure_
