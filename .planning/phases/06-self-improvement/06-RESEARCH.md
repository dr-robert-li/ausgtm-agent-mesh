# Phase 6: Self-Improvement (real loop) - Research

**Researched:** 2026-06-07
**Domain:** Governed self-evolving agents — held-out evaluation harness, GEPA-style offline inert proposer, CycloneDX ML-BOM on promotion, non-hot versioned promotion + rollback (Option C)
**Confidence:** HIGH (repo seams + installed-dep API surface verified in-tree; external SOTA already settled by the commissioned deep-research report — not re-surveyed here)

## Summary

This phase does NOT need a fresh SOTA survey — that was done (06-CONTEXT Canonical References → Research, 23 verified primary-source claims). This research grounds those locked decisions into THIS repo's concrete seams and **verifies the two version-sensitive claims the report flagged**:

1. **Langfuse experiment runner + dataset-version pinning is present in the installed version.** `langfuse==4.7.1` (pinned `langfuse>=4,<5` in `pyproject.toml`) exposes `Langfuse.run_experiment(...)` (item-level `evaluators`, run-level `run_evaluators`, `composite_evaluator`), `get_dataset(name, version=<datetime>)`, and dataset-run methods. The report's "dataset-version pinning coming shortly (Sept 2025)" flag is **RESOLVED**: pinning is available via the public `get_dataset(..., version=...)` path. `[VERIFIED: in-tree inspection of .venv langfuse 4.7.1]`
2. **`run_experiment` runs creds-free over local data.** Verified empirically: with NO Langfuse keys the client initializes "disabled" (no trace upload) but `run_experiment(data=[LocalExperimentItem...], task=..., evaluators=...)` still executes the task fn + evaluators locally and returns a full `ExperimentResult` with `item_results`. **This is the linchpin that reconciles D-01 (harness = Langfuse experiment runner) with D-14/criterion-6 (default suite stays creds-free).** `[VERIFIED: in-tree execution]`
3. **CycloneDX ML-BOM has a real conformance gap.** `cyclonedx-python-lib==11.8.0` supports `SchemaVersion.V1_7` and `ComponentType.MACHINE_LEARNING_MODEL`, but has **no `ModelCard` data model** (upstream issue #912 still open). Full ECMA-424 v1.7 model cards cannot be emitted via the library's typed models — carry prompts/dataset-version/eval-results as CycloneDX `properties` / `external_references` on a `machine-learning-model` component. This is exactly the "keep conformance pragmatic" posture D-11 already authorizes. `[VERIFIED: PyPI + readthedocs + GitHub #912]`

**Primary recommendation:** Build the harness as **two layers**: a pure-Python, creds-free **no-regression gate** over `ExperimentResult` (default lane), and a thin `live`-lane wrapper that swaps in a real-model task fn + LLM-judge `run_evaluators`. Keep the held-out set in a **distinct dataset/pool** the proposer never reads. Add `cyclonedx-python-lib` as an **optional extra** and emit V1_7 + `machine-learning-model` + `properties`. Implement non-hot wiring as a **boot-time cached version pin** (NOT `get_settings()`-at-call-time, NOT `get_prompt_with_fallback`-at-call-time).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SI-01 | Real eval harness replaces `evaluate_proposal` stub; Langfuse experiment run over a versioned held-out dataset; item+run no-regression vs baseline | `run_experiment` verified present & creds-free over local data; `evaluate_proposal` stub at `self_improvement.py:149` is the swap site; `EvaluationResult` model already carries `checks`/`passed`/`evaluator` |
| SI-01a | Scored on held-out set **distinct from the proposer's optimization signal**; gate never reads the optimization signal | Two-pool design: proposer mines `repo.list_tool_calls`/task records (train/dev); gate reads a separate held-out dataset; zero-overlap assertion test (anti-reward-hack) |
| SI-01b | Promotion-eligibility = candidate ≥ baseline on aggregate AND no item-level regression beyond threshold | Pure-Python gate over `ExperimentResult.item_results`; baseline stored as a prior run/golden; item-level drill-down mandatory (avg can mask per-item regressions) |
| SI-01c | Held-out items are deterministic frozen-context snapshots → candidate & baseline scored on identical inputs | Freeze context into `LocalExperimentItem.input` (deterministic replay); MIRAGE-Bench is **inspiration only** — do not harden into a must-have |
| SI-01d | LLM-judge dimension `live`-only: position-bias control (order-swap), human-calibrated TPR/FPR, finite-sample Type-I gate, never sole arbiter at close margins; default suite creds-free | Lives entirely in `live` lane behind `live_creds` fixture as `run_evaluators`; default lane uses deterministic evaluators only |
| SI-02 | Promotion generates AI-BOM snapshot + controlled versioned (non-hot) promotion; rollback retained; no runtime mutation | `promote_proposal` (`:235`) fills `ai_bom_snapshot_id`; `AIBOMSnapshot` model exists; non-hot loader is a new boot-time seam |
| SI-02a | Snapshot is CycloneDX ML-BOM (ECMA-424 v1.7) from deployment + tool-pack manifests, bound to promoted version, retained | `cyclonedx-python-lib` V1_7 + `machine-learning-model`; ModelCard gap → use `properties`/`external_references`; sources = `manifests/*.yaml` |
| SI-02b | Promoted artifact referenceable only via versioned non-hot wiring read at next start/deploy; rollback re-points active version to `previous_version`; both proven by tests | Boot-time cached version pin seam; `rollback_promotion` (`:297`) re-points pointer; deterministic tests (no creds) |
| SI-03 | GEPA-style log-driven reflective proposer as **separated offline meta-agent**; mines traces, emits **inert** prompt/workflow diffs only; bounded iteration-capped loop re-validates on held-out each round (held-out protected from proposer) | `reflect_on_task` (`:110`) is the production seam; offline module, NOT inline in LangGraph supervisor; durable source = Postgres `tool_calls`/task records; inertness proven creds-free with a stub reflector |
</phase_requirements>

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Harness = Langfuse experiment runner (`experiments-via-sdk`) over a **versioned held-out dataset**, recording item-level + run-level evaluators. Replaces the boolean `evaluate_proposal` stub as the scoring engine.
- **D-02 (anti-reward-hack):** Score on a held-out task set **DISTINCT from any signal the proposer optimized against**. Never gate on the optimization signal.
- **D-03 (no-regression gate):** Promotion-eligibility = candidate ≥ baseline on aggregate gate metrics **AND** no item-level regression beyond a configured threshold. Use baseline-vs-candidate compare (green/red deltas).
- **D-04 (deterministic items):** Held-out items are **deterministic frozen-context snapshots** so candidate and baseline see identical inputs.
- **D-05 (LLM-judge — opt-in lane only):** LLM-judge runs **only** in the `live` lane; **position-bias control (order-swap)**; never sole arbiter for close-margin proposals.
- **D-06 (judge calibration + statistical gate):** LLM-judge gate calibrated against a small human-labelled set (TPR/FPR), with a **statistically valid below-threshold / finite-sample Type-I error gate**. Calibration set must match the promotion task distribution. `live`-lane only.
- **D-07 (proposer = GEPA-style, offline, separated):** Log-driven reflective proposer samples execution traces, reflects in natural language, emits **prompt/workflow diffs only**. **Separated meta-agent** — NOT wired inline into the live task supervisor. `reflect_on_task(...)` is the seam.
- **D-08 (inert):** Proposer mutates nothing live; produces structured `SelfImprovementProposal` artifacts; nothing executes on creation.
- **D-09 (bounded loop):** Loop **caps optimization iterations** and **re-validates on the held-out set each round**. Held-out set protected from proposer visibility.
- **D-10 (DGM out of scope):** No autonomous self-code-rewriting / autonomous benchmark-gated acceptance. Acceptance is human-gated, non-hot.
- **D-11 (ML-BOM shape):** Promotion generates a **CycloneDX ML-BOM** (ECMA-424 v1.7) from deployment + tool-pack manifests, capturing prompts / tools / models / model-routes / dataset version / eval results, bound to the promoted version, retained 12 months. Fills `PromotionRecord.ai_bom_snapshot_id`. **Full conformance is an enhancement over the literal bar — keep conformance pragmatic.**
- **D-12 (non-hot wiring):** Promoted artifact referenceable **only via versioned, non-hot wiring read at next start/deploy**; a loader seam reads the active version at boot; promotion does NOT hot-swap running config. Proven by test.
- **D-13 (rollback):** `rollback_promotion(...)` re-points the active version pointer to `previous_version` (not merely a status flip). Proven by test.
- **D-14 (test lanes):** Default `make test` (`pytest -m "not live"`) stays **creds-free** — deterministic harness, no-regression gates, ML-BOM generation, promotion/rollback wiring all run here. `live` lane (`make test-live`) carries LLM-judge + calibration + real-model scoring.
- **D-15:** Requirement edits already applied to REQUIREMENTS.md + ROADMAP (SI-01a–d, SI-02a–b, SI-03; deferred SI-04/SI-05).

### Claude's Discretion
- Exact iteration cap, held-out dataset size, calibration-set size, alpha / below-threshold failure-rate numbers (method established by research, not POC numerics).
- Held-out dataset versioning / refresh / contamination-protection mechanism.
- Specific CycloneDX ML-BOM field mapping for LangGraph checkpoints / Deep Agents roster / Langfuse prompt+dataset versions; whether to also map to NIST AI RMF / ISO-42001 (only CycloneDX surfaced a confirmed primary-source claim).

### Deferred Ideas (OUT OF SCOPE)
- **SI-04** (→ new milestone "Self-Evolving Surfaces"): Memory growth/compression + skill-library promotion as governed proposals (needs memory-poisoning regression controls).
- **SI-05** (→ same milestone): Multi-agent topology / routing-depth evolution as governed proposals (needs co-evolutionary-drift controls).
- DGM-style autonomous self-code modification — permanently excluded by Option C.
- Full NIST AI RMF / ISO-42001 control mapping — only CycloneDX confirmed for the POC.
- PROJECT.md milestone-goal rewrite + `/gsd:new-milestone` for "Self-Evolving Surfaces" — surfaced follow-up, NOT part of Phase 6 plans.
</user_constraints>

## Project Constraints (from CLAUDE.md)

These carry the same authority as locked decisions. Research must not recommend any approach that contradicts them.

- **Option C only / no runtime autonomous self-modification** (§1, §4, §8). Proposals are inert; promotion is the single human-gated, **non-hot** chokepoint; no runtime mutation of active instructions/permissions/routing.
- **Write-approval gate holds for every write-class action, payload-hash bound** (§8). A prompt/tool/route/policy change *is itself a write* → goes under the same gate. Already implemented for promotion via `open_promotion_approval` + payload-hash rebind in `promote_proposal`.
- **Deep Agents roster stays bounded and declared** (planner, researcher/tool-router, code-writer, reviewer) — no uncontrolled self-spawning (§8). The GEPA proposer is a **separated offline meta-agent / reviewer-role step**, NOT a new unbounded live agent (D-07, docs §3).
- **Required stack: LangChain + LangGraph + Deep Agents + Langfuse; LangSmith NEVER a dependency** (§1). The harness builds on Langfuse experiments/datasets — already the required observability plane.
- **Durable stores stay in `australia-southeast1`; 12-month retention** for AI-BOM/approvals/audit. `migrations/0002_self_improvement.sql` is append-only governance.
- **Tenant-scoping on all repo reads** (DUR-02). Eval/proposal/promotion/trace-mining queries pass `tenant_id` (e.g. `list_evaluations(proposal_id, tenant_id)`, `list_tool_calls(task_id, tenant_id)`).

*No `.claude/skills/` rules directory found in this repo — no additional project-skill patterns to honour.*

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Held-out scoring run (real model) | Execution plane (worker / `live` lane) | Langfuse (trace+eval store) | Real-model task fn needs creds → `live`; Langfuse stores the experiment run |
| No-regression gate (aggregate + item-level) | Pure service logic (`self_improvement.evaluate_proposal`) | Durable store (baseline) | Deterministic comparison over `ExperimentResult`; runs default lane, creds-free |
| GEPA reflective proposer (real reflection LLM call) | Separated offline meta-agent (`live` lane) | Postgres (durable trace source) | LLM call → `live`; trace mining reads durable `tool_calls`/task records, NOT live spans |
| Proposer inertness + plumbing | Service logic (`reflect_on_task`) | — | Stub reflector proves inertness creds-free; mirrors `_RecordingRouter` pattern |
| CycloneDX ML-BOM generation | Governance/service logic (new generator) | Manifests (`deployment` + `tool_pack`) | Pure transform manifest+metadata → CycloneDX JSON; creds-free, default lane |
| Non-hot version pin (boot-time loader) | Settings/boot seam (new) | Durable promotion record | Read once at start/deploy; never re-read mid-run; promotion does not hot-swap |
| Promotion / rollback ledger | Service logic + durable store | Approval ledger (payload-hash) | Existing `promote_proposal`/`rollback_promotion`; append-only `0002` tables |

## Standard Stack

### Core (already installed / pinned — VERIFY, do not re-add)
| Library | Installed | Pin in pyproject | Purpose | Notes |
|---------|-----------|------------------|---------|-------|
| `langfuse` | **4.7.1** | `langfuse>=4,<5` (runtime extra) | Experiment runner (`run_experiment`), versioned datasets (`get_dataset(version=)`), evaluators, prompt/version mgmt | `[VERIFIED: .venv inspection + pip index]` — `run_experiment`/`get_dataset`/`run_evaluators` all present; v4 import paths only (`langfuse.langchain`, NOT v2 `langfuse.callback`) |
| `langchain` / `langgraph` / `deepagents` | 1.3.4 / 1.2.4 / 0.6.8 | `agents` extra | Proposer meta-agent harness (reviewer-role), supervisor routing | `[VERIFIED: pip list]` — proposer is offline/separated, NOT a new live supervisor agent |
| `pydantic` | 2.x | `>=2.6` core | `SelfImprovementProposal`/`EvaluationResult`/`PromotionRecord`/`AIBOMSnapshot` models | Already defined in `contracts/models.py` |

### Supporting (NEW dependency to add)
| Library | Version | Purpose | When/how to add |
|---------|---------|---------|-----------------|
| `cyclonedx-python-lib` | **11.8.0** (latest; min `>=8` for V1_7 schema + `machine-learning-model`) | Emit CycloneDX ML-BOM (SI-02a) with valid structure, `SchemaVersion.V1_7`, `ComponentType.MACHINE_LEARNING_MODEL`, `JsonV1Dot7` output | Add as a dedicated **optional extra** (e.g. `aibom = ["cyclonedx-python-lib>=8,<12"]`). MUST be importable in the **default lane** for the creds-free ML-BOM test → install it in the test/runtime env, but keep it out of the minimal contract-only env. It needs **no creds** (pure data-model + serializer). `[VERIFIED: PyPI pip index 11.8.0; readthedocs autoapi for ComponentType; GitHub schema/__init__.py for V1_7]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `cyclonedx-python-lib` (typed models) | Hand-emit conformant CycloneDX 1.7 JSON | Hand-emit avoids a dep and dodges the ModelCard gap entirely, but you re-implement schema validity + risk drift. **Recommendation: use the library for structure (it guarantees valid 1.7 + correct component type) and carry ML metadata as `properties` — best of both.** |
| `run_experiment` for the gate | Custom pure-Python runner over frozen items | `run_experiment` already runs creds-free over local data AND gives Langfuse traces when creds exist — no reason to hand-roll. Keep the **gate** (comparison logic) separate and pure-Python regardless. |
| `_dataset_version=` kwarg on `run_experiment` | `get_dataset(name, version=<datetime>)` then pass items to `run_experiment(data=...)` | `_dataset_version` is **underscore-prefixed / semi-private** and may break across minors. **Use the public `get_dataset(..., version=...)` path.** `[VERIFIED: signature inspection]` |

**Installation (add the extra, then install into the test/runtime env):**
```bash
# pyproject.toml [project.optional-dependencies]
# aibom = ["cyclonedx-python-lib>=8,<12"]
python -m pip install -e ".[aibom]"
```

## Package Legitimacy Audit

> slopcheck install was correctly **denied** by the sandbox (read-only research task should not install an undeclared agent-chosen tool). Legitimacy assessed via authoritative primary sources instead; per protocol graceful-degradation, the new package is tagged `[ASSUMED]` and the planner SHOULD gate its first install behind a `checkpoint:human-verify` task. Existing pinned deps were already vetted in prior phases' research and are unchanged here.

| Package | Registry | Age / Releases | Source Repo | slopcheck | Disposition |
|---------|----------|----------------|-------------|-----------|-------------|
| `cyclonedx-python-lib` | PyPI (11.8.0, latest 2026-06-04) | 100+ releases since 0.0.1; OWASP CycloneDX official project | `github.com/CycloneDX/cyclonedx-python-lib` | n/a (not run) | **Approved — `[ASSUMED]`, gate first install behind `checkpoint:human-verify`** |
| `langfuse` 4.7.1 | PyPI | already pinned/installed (prior phase) | `github.com/langfuse/langfuse-python` | n/a | Approved (unchanged) |
| `langchain`/`langgraph`/`deepagents` | PyPI | already pinned/installed | official repos | n/a | Approved (unchanged) |

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none. `cyclonedx-python-lib` is the OWASP CycloneDX reference library — low slop risk; the only caveat is the **ModelCard feature gap** (functionality, not legitimacy). Verify on PyPI as `cyclonedx-python-lib` (the `cyclonedx-bom` package is the *CLI tool*, a different package — do not confuse them).

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────── OFFLINE / SEPARATED (NOT the live supervisor) ───────────────────┐
                         │                                                                                       │
 completed task runs     │   GEPA reflective proposer (06-02)            held-out dataset (06-01)                │
 ──────────────────►  durable Postgres            ── reads train/dev ──►  reflect (NL diagnose)   ║ PROTECTED ║  │
 (tool_calls,            │   trace source                  pool          emits prompt/workflow      from        │
  task records,          │   repo.list_tool_calls()      ───────────►    DIFF (inert)            ─► proposer    │
  evidence_chunks)       │   (tenant-scoped)                              SelfImprovementProposal   visibility  │
                         │                                                  status=DRAFT             (06-01a)    │
                         │                                                      │                                │
                         │   bounded loop: cap N iterations ◄───────────────────┤                               │
                         │   re-validate each round on HELD-OUT ────────────────┘                               │
                         └───────────────────────────────────────────────────────────────────────────────────┘
                                                            │ (DRAFT proposal persisted; nothing live changed)
                                                            ▼
   evaluate_proposal (06-01)  ── builds frozen LocalExperimentItems (deterministic, 06-01c) ──►
        ├─ DEFAULT LANE (creds-free): run_experiment(task=stub, evaluators=deterministic) → ExperimentResult
        │        └─ no-regression GATE (pure-Python): candidate ≥ baseline aggregate AND no item regression>θ (06-01b)
        └─ LIVE LANE (live_creds): task=real-model, run_evaluators=LLM-judge(order-swap, calibrated, Type-I) (06-03)
                                                            │ EvaluationResult.passed
                                                            ▼
   open_promotion_approval ── LangGraph interrupt → shared approval ledger (payload-hash bound) ── HUMAN ──►
                                                            │ APPROVED (hash still matches artifact)
                                                            ▼
   promote_proposal (06-04/05) ── generate CycloneDX ML-BOM (V1_7) from manifests ──► AIBOMSnapshot.snapshot_id
        ├─ PromotionRecord{promoted_version, previous_version, ai_bom_snapshot_id}   (append-only, 12mo)
        └─ NON-HOT: running config UNCHANGED. boot-time version pin (06-05) reads active version only at next start.
                                                            │
   rollback_promotion ── re-point active version pointer → previous_version (06-05) ──► next start reads restored
```

### Recommended Module Layout (additive — fit existing `services/` convention)
```
src/agent_mesh/services/
├── self_improvement.py        # EXISTS — swap evaluate_proposal body; reflect_on_task stays the seam
├── eval_harness.py            # NEW (06-01) — frozen-item builder, run_experiment wrapper, no-regression gate
├── reflective_proposer.py     # NEW (06-02) — offline GEPA proposer + bounded loop; calls reflect_on_task
├── ai_bom.py                  # NEW (06-04) — CycloneDX ML-BOM generator from manifests → AIBOMSnapshot
└── version_pin.py             # NEW (06-05) — boot-time cached active-version loader (non-hot)
src/agent_mesh/eval/
└── judges.py                  # NEW (06-03) — live-lane LLM-judge: order-swap, calibration, Type-I gate
tests/
├── test_eval_harness.py       # NEW — default lane: frozen-item determinism, no-regression gate
├── test_reflective_proposer.py# NEW — default lane: inertness (stub reflector), held-out non-overlap
├── test_ai_bom.py             # NEW — default lane: valid CycloneDX 1.7 JSON, ML component, manifest mapping
├── test_version_pin.py        # NEW — default lane: promotion non-hot proof + rollback re-point proof
└── test_judges_live.py        # NEW — @pytest.mark.live: order-swap, calibration, Type-I (live_creds)
```

### Pattern 1: Creds-free experiment runner over frozen local items (06-01)
**What:** Use `run_experiment` with `LocalExperimentItem` dicts and a deterministic task fn so the default lane scores without a model or a host.
**When to use:** The default-lane harness body of `evaluate_proposal`.
```python
# Source: [VERIFIED: in-tree langfuse 4.7.1 signatures + executed creds-free]
from langfuse import Langfuse
from langfuse.experiment import Evaluation
# LocalExperimentItem fields: {"input": Any, "expected_output": Any, "metadata": dict|None}

def deterministic_task(*, item, **_):          # no model → creds-free
    return apply_candidate_offline(item["input"])   # frozen-context replay (06-01c)

def exact_match(*, input, output, expected_output, metadata, **_) -> Evaluation:
    # Evaluation(name, value:int|float|str|bool, comment=None, metadata=None,
    #            data_type="NUMERIC"|"CATEGORICAL"|"BOOLEAN", config_id=None)
    return Evaluation(name="exact_match", value=float(output == expected_output))

lf = Langfuse()  # disabled (no keys) → no upload, but run_experiment still executes locally
result = lf.run_experiment(
    name="si-candidate", data=frozen_items, task=deterministic_task, evaluators=[exact_match],
)
# result.item_results carries per-item scores → feed the pure-Python no-regression gate
```

### Pattern 2: Pure-Python no-regression gate (06-01b) — the actual promotion-eligibility check
**What:** Compare candidate vs a stored baseline both at aggregate AND item level. Aggregate alone hides item regressions ("a 4% avg gain can hide a 16% per-item regression" — D-03).
```python
# Source: [CITED: 06-CONTEXT D-03] design; pure stdlib, default lane
def passes_no_regression(candidate, baseline, *, item_threshold: float) -> tuple[bool, list[dict]]:
    if mean(candidate.scores) < mean(baseline.scores):          # aggregate gate
        return False, [{"reason": "aggregate_below_baseline"}]
    regressions = [
        {"item_id": i, "delta": c - b}
        for i, (c, b) in items_zipped(candidate, baseline)
        if (b - c) > item_threshold                             # item-level drill-down
    ]
    return (not regressions), regressions
```
**Baseline source:** the promoted-version's prior run (or a committed golden `EvaluationResult`). Store baseline scores alongside the promoted version so the gate is reproducible offline.

### Pattern 3: Held-out / optimization-signal separation (06-01a, the anti-reward-hack invariant)
**What:** Two *disjoint* item pools. The proposer reads only the train/dev pool (mined from Postgres traces); the gate reads only the held-out pool. A test asserts **zero item-ID overlap**.
```python
# Source: [CITED: 06-CONTEXT D-02/D-09]; reward hacking worsens with iterations
def assert_holdout_isolation(train_ids: set[str], holdout_ids: set[str]) -> None:
    assert not (train_ids & holdout_ids), "held-out set leaked into proposer optimization signal"
```
This invariant **spans 06-01 and 06-02** — neither plan owns it alone; surface it as a shared cross-plan check.

### Pattern 4: Offline inert proposer mining the DURABLE store (06-02)
**What:** Mine `repo.list_tool_calls(task_id, tenant_id)` + task records (durable Postgres) — NOT live Langfuse spans — so the proposer is reproducible offline and creds-free for the inertness test. The real reflection LLM call is `live`-lane; the plumbing (returned proposal is `DRAFT`, nothing promoted) is tested with a **stub reflector** mirroring the `_RecordingRouter` pattern in `conftest.py`.
```python
# Source: [VERIFIED: repository.py list_tool_calls is tenant-scoped]
def propose_from_traces(repo, task, reflect_fn) -> SelfImprovementProposal:
    evidence = repo.list_tool_calls(task.task_id, task.tenant_id)   # durable, tenant-scoped
    diff = reflect_fn(evidence)             # live: real LLM; default test: stub returns canned diff
    return si.reflect_on_task(repo, task, proposal_type=..., proposed_patch=diff, ...)  # status=DRAFT
```
**Inertness assertion (default lane):** `assert proposal.status == ProposalStatus.DRAFT` and no `PromotionRecord` exists.

### Pattern 5: Non-hot boot-time version pin (06-05) — NOT call-time
**What:** Read the active promoted version **once at boot** and cache it; do NOT use `get_settings()` (rebuilds from env each call) or `get_prompt_with_fallback` (pulls at call time) — both are call-time patterns that would behave like hot-swapping.
```python
# Source: [VERIFIED: settings.get_settings() rebuilds Settings() per call → wrong for non-hot]
_ACTIVE_VERSION: str | None = None   # module-level cache, set once

def load_active_version_at_boot(repo, tenant_id) -> str:
    global _ACTIVE_VERSION
    _ACTIVE_VERSION = repo.current_active_version(tenant_id)  # read at start/deploy only
    return _ACTIVE_VERSION

def active_version() -> str | None:
    return _ACTIVE_VERSION   # never re-reads the store mid-run
```
**Non-hot proof test (default lane):** promote → assert `active_version()` is UNCHANGED until an explicit `load_active_version_at_boot()` (reload/boot) call → then it reflects the new version. **Rollback proof:** `rollback_promotion` re-points the stored active pointer to `previous_version`; the next `load_active_version_at_boot()` returns the restored version.

### Pattern 6: CycloneDX ML-BOM with the ModelCard gap worked around (06-04)
**What:** Emit a valid CycloneDX 1.7 BOM; represent the promoted model/prompt bundle as a `machine-learning-model` component; carry prompts/dataset-version/eval-results as `Property` entries / `ExternalReference`s (since the library has no `ModelCard` model — issue #912).
```python
# Source: [VERIFIED: cyclonedx schema/__init__.py V1_7; readthedocs ComponentType.MACHINE_LEARNING_MODEL; #912 no ModelCard]
from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.model import Property
from cyclonedx.schema import SchemaVersion, OutputFormat
from cyclonedx.output import make_outputter

bom = Bom()
ml = Component(name="planner-prompt-bundle", type=ComponentType.MACHINE_LEARNING_MODEL,
               version=promoted_version)
ml.properties.update({
    Property(name="agentmesh:dataset_version", value=dataset_version_iso),
    Property(name="agentmesh:eval_result_id", value=evaluation_id),
    Property(name="agentmesh:model_route_profile", value=route_profile),
    # prompts/tools/models pulled from manifests/deployment.manifest.yaml + tool_pack_manifest.yaml
})
bom.components.add(ml)   # add tool components from tool_pack_manifest similarly
json_str = make_outputter(bom, OutputFormat.JSON, SchemaVersion.V1_7).output_as_string()
# persist json_str → AIBOMSnapshot, set PromotionRecord.ai_bom_snapshot_id
```
**Pragmatic conformance (D-11):** Criterion 4 literally needs "a snapshot from the manifests." V1_7 + `machine-learning-model` + properties IS conformant CycloneDX; full ECMA-424 model cards are explicitly out (acceptable). Verify the exact import paths against the installed version at plan time — `make_outputter`/`output` API has shifted across major versions; pin and confirm.

### Anti-Patterns to Avoid
- **Using `run_experiment` as the gate.** The runner executes the task and scores items; it does NOT decide promotion-eligibility. Keep the no-regression decision in pure Python so it is reproducible and creds-free.
- **Wiring the proposer into the live LangGraph supervisor.** Violates D-07 + CLAUDE.md bounded-roster. It is a **separated offline meta-agent / reviewer-role** that emits inert proposals.
- **Reading the active version via `get_settings()` or at call time.** That is effectively hot-swapping. Non-hot = read once at boot, cache.
- **Letting the proposer see the held-out set.** Direct reward-hacking vector (D-02). Enforce + test zero overlap.
- **Tagging cyclonedx ML-BOM as needing creds / a network.** It is a pure data-model serializer → default lane.
- **Using `langfuse.callback` (v2 import).** DEAD under 4.x — use `langfuse.langchain` / top-level `langfuse` (already handled in `observability.py`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Experiment execution + per-item tracing | Custom run loop + trace uploader | `langfuse.run_experiment` | Already creds-free over local data; gives Langfuse traces for free when creds exist |
| Dataset version pinning | Custom snapshot/version table | `get_dataset(name, version=<datetime>)` | Public API present in 4.7.1; report's "coming shortly" flag resolved |
| CycloneDX 1.7 document structure | Hand-rolled JSON schema | `cyclonedx-python-lib` typed models + `make_outputter` | Guarantees valid 1.7; only ML *model-card* metadata needs the properties workaround |
| Approval / payload-hash binding for promotion | New approval flow | EXISTING `approvals.open_approval` + `is_approved` (reused in `open_promotion_approval`/`promote_proposal`) | Already tested (hash-rebind), already CLAUDE.md-compliant |
| Promotion / rollback ledger | New tables | EXISTING `0002_self_improvement.sql` + `PromotionRecord` | Append-only, 12-month, tenant-partitioned already |

**Key insight:** ~80% of Phase 6's pipeline already exists (reflect→evaluate→approve→promote→rollback with hash-rebind). The phase is **four targeted insertions** (real gate body, offline proposer, ML-BOM generator, non-hot loader) into a working skeleton — not a rebuild.

## Runtime State Inventory

> Phase 6 is additive (new code + one new optional dep), not a rename/refactor/migration. No stored-string rename, no live-service reconfiguration, no OS-registered state changes.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — `0002_self_improvement.sql` tables already exist and match the contract models; no schema change forced (a `current_active_version` pointer for 06-05 may be a new tiny table/row — additive migration `0003`) | Possible additive migration `0003` for the active-version pointer; no data migration |
| Live service config | None — no Langfuse/Cloudflare/GCP live reconfiguration; harness/proposer are creds-free in default lane | None |
| OS-registered state | None | None |
| Secrets/env vars | No new secret *values*; `live` lane reuses existing `ANTHROPIC_API_KEY`/`VERTEX_PROJECT_ID`/`CF_AIG_WRAPPER_URL` via `live_creds` | None |
| Build artifacts | New optional extra `[aibom]` → `cyclonedx-python-lib` must be installed into test/runtime env for the default-lane ML-BOM test to import | `pip install -e ".[aibom]"` in the env that runs `make test` |

## Common Pitfalls

### Pitfall 1: Default suite goes red because the harness "needs Langfuse creds"
**What goes wrong:** Treating `run_experiment` as creds-required and pushing the whole harness to `live`, breaking criterion 6 / D-14.
**Why it happens:** Assuming the experiment runner uploads/needs a host.
**How to avoid:** It runs creds-free over local data (verified). Default lane: stub task fn + deterministic evaluators + pure-Python gate. Only the real-model task fn and LLM-judge `run_evaluators` are `live`.
**Warning signs:** `evaluate_proposal` importing `live_creds` or skipping in `make test`.

### Pitfall 2: ML-BOM ModelCard import error
**What goes wrong:** Code imports a `ModelCard` class from `cyclonedx-python-lib` → ImportError; full ECMA-424 model card not representable.
**Why it happens:** The spec has model cards; the Python library doesn't (issue #912).
**How to avoid:** Use `ComponentType.MACHINE_LEARNING_MODEL` + `Property`/`ExternalReference` for ML metadata. Don't promise full model-card conformance (D-11 already scopes this out).
**Warning signs:** Searching the lib for `model_card` / `modelCard` (returns nothing).

### Pitfall 3: Non-hot wiring implemented as call-time read (silent hot-swap)
**What goes wrong:** Active version read via `get_settings()`/`get_prompt_with_fallback` each call → a promotion immediately affects running behavior → violates D-12 + criterion 5 + CLAUDE.md no-runtime-mutation.
**Why it happens:** Copying the existing call-time fallback pattern.
**How to avoid:** Module-level cached pin read once at boot; deterministic test that promotion does NOT change `active_version()` until an explicit reload.
**Warning signs:** No boot/reload step in the non-hot test; `active_version()` reading the DB.

### Pitfall 4: Held-out set leaks into the proposer
**What goes wrong:** Proposer optimizes against the gate's items → reward hacking (research: 26.4%→57.8% as steps 10→100).
**Why it happens:** Single shared dataset for mining and gating.
**How to avoid:** Disjoint pools + zero-overlap assertion test (Pattern 3).
**Warning signs:** Same dataset name passed to both proposer trace-mining and the gate.

### Pitfall 5: `cyclonedx-bom` vs `cyclonedx-python-lib` confusion
**What goes wrong:** Installing `cyclonedx-bom` (the CLI tool) expecting the data-model library.
**How to avoid:** The library with the typed models is `cyclonedx-python-lib`. Verify the import is `import cyclonedx.model...`.

### Pitfall 6: `_dataset_version=` private-API breakage
**What goes wrong:** Pinning via the underscore-prefixed `run_experiment(_dataset_version=...)` kwarg → breaks on a langfuse minor bump.
**How to avoid:** Pin via public `get_dataset(name, version=<datetime>)`, then pass items to `run_experiment(data=...)`.

## State of the Art

| Old Approach (POC scaffold today) | Current Approach (this phase) | Source |
|-----------------------------------|-------------------------------|--------|
| `evaluate_proposal` = boolean deterministic stub / `pending` | Real held-out experiment harness + item+run no-regression gate | D-01/D-03; `self_improvement.py:149` |
| No live proposer (`reflect_on_task` seam unused by orchestration) | GEPA-style offline reflective proposer + bounded loop (inert) | D-07; arXiv:2507.19457 (GEPA > RL ~6%, up to 20%, 35x fewer rollouts) |
| `ai_bom_snapshot_id` link unfilled; no generator | CycloneDX ML-BOM (V1_7) generated from manifests on promotion | D-11; cyclonedx.org ECMA-424 v1.7 |
| Promotion records version but no wiring; rollback = status flip | Non-hot boot-time version pin; rollback re-points active pointer | D-12/D-13 |

**Deprecated/outdated:**
- Langfuse v2 `from langfuse.callback import CallbackHandler` — DEAD under 4.x (already avoided in `observability.py`).
- The report's "dataset-version pinning coming shortly (Sept 2025)" caveat — **superseded**: present in installed 4.7.1.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `cyclonedx-python-lib` is the right dep and is legitimate (slopcheck not run — install denied) | Package Legitimacy Audit | Low — OWASP official project; planner gates first install behind `checkpoint:human-verify` |
| A2 | `cyclonedx-python-lib`'s output API is `make_outputter(bom, OutputFormat.JSON, SchemaVersion.V1_7)` | Pattern 6 | Medium — output API shifted across majors; **confirm exact import at plan/impl time against the installed version** |
| A3 | Baseline for the no-regression gate can be stored as a prior `EvaluationResult`/golden alongside the promoted version | Pattern 2 | Low — additive storage; may need a small `0003` migration or a JSON column |
| A4 | A `current_active_version` pointer (06-05) is a small additive table/row, not a contract change | Runtime State Inventory / Pattern 5 | Low — additive migration `0003` |
| A5 | Frozen-context determinism (SI-01c) is achievable by freezing inputs into `LocalExperimentItem.input` (deterministic replay), without hardening MIRAGE-Bench | Pattern 1 | Low — task explicitly says don't harden MIRAGE-Bench if deterministic replay suffices |

**Note:** External SOTA claims (GEPA, reward-hacking rates, position bias, calibration, MIRAGE-Bench, CycloneDX ECMA-424) are `[CITED]` from the commissioned deep-research report (06-CONTEXT Canonical References, 23 verified primary sources) — not re-verified this session per the objective.

## Open Questions

1. **Exact gate numerics (iteration cap, held-out size, item-threshold θ, judge alpha/TPR-FPR).**
   - Known: Claude's Discretion (D-15) + research establishes the *method*, not POC numbers.
   - Recommendation: planner picks conservative defaults (e.g. iteration cap = 3–5, held-out ≥ 10 frozen items, θ as a configurable setting); make them config-driven, not hardcoded.

2. **Where the baseline scores live for reproducible offline gating.**
   - Known: must be readable creds-free in the default lane.
   - Recommendation: store the promoted version's `EvaluationResult` (or a committed golden JSON fixture) keyed by version; gate reads it offline. Possibly `0003` migration.

3. **`current_active_version` storage shape (06-05).**
   - Recommendation: a tiny tenant-scoped pointer table (or reuse latest non-rolled-back `PromotionRecord.promoted_version`) read once at boot. Decide whether rollback writes a new pointer row or flips state.

4. **CycloneDX output API exact symbols in installed version.**
   - Recommendation: at impl time, `python -c "from cyclonedx.output import make_outputter; from cyclonedx.schema import SchemaVersion, OutputFormat"` to confirm before writing the generator (see A2).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `langfuse` (SDK, runner) | SI-01 harness | ✓ | 4.7.1 | — (runner works creds-free locally) |
| `cyclonedx-python-lib` | SI-02a ML-BOM | ✗ (not yet installed) | target 11.8.0 / `>=8` | Hand-emit conformant JSON (avoids dep) |
| Langfuse host + keys | `live`-lane judge / trace upload | ✗ (default) | — | `live_creds` skips cleanly; default lane is creds-free |
| Anthropic / Vertex creds | `live`-lane real-model scoring + GEPA reflection | ✗ (default) | — | `live_creds` fixture skips; stub task/reflector in default lane |
| Postgres | durable trace source / promotion ledger | ✗ (default uses in-memory repo) | — | In-memory `Repository` (default suite); `pg_dsn` gates DB tests |

**Missing dependencies with no fallback:** none (every gap has a creds-free / in-memory / hand-emit fallback).
**Missing dependencies with fallback:** `cyclonedx-python-lib` (→ hand-emit JSON); live creds (→ `live_creds` skip).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x (`[tool.pytest.ini_options]`, `pythonpath=["src"]`, `testpaths=["tests"]`) |
| Config file | `pyproject.toml` |
| Quick run command | `make test` → `pytest -q -m "not live"` (creds-free) |
| Full suite command | `make test` (default) + `make test-live` → `pytest -q -m live` (opt-in, `live_creds`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SI-01 | `evaluate_proposal` runs a real experiment over frozen items, returns pass/fail | unit (default) | `pytest tests/test_eval_harness.py -m "not live"` | ❌ Wave 0 |
| SI-01a | Held-out vs train pools have zero overlap | unit (default) | `pytest tests/test_reflective_proposer.py::test_holdout_isolation` | ❌ Wave 0 |
| SI-01b | Candidate < baseline aggregate → fail; per-item regression > θ → fail | unit (default) | `pytest tests/test_eval_harness.py::test_no_regression_gate` | ❌ Wave 0 |
| SI-01c | Same frozen item → identical input to candidate & baseline (deterministic) | unit (default) | `pytest tests/test_eval_harness.py::test_frozen_items_deterministic` | ❌ Wave 0 |
| SI-01d | LLM-judge order-swap + calibration + Type-I gate; never in default suite | live | `pytest tests/test_judges_live.py -m live` | ❌ Wave 0 |
| SI-02 / SI-02a | Promotion produces a valid CycloneDX 1.7 ML-BOM from manifests; `ai_bom_snapshot_id` filled | unit (default) | `pytest tests/test_ai_bom.py` | ❌ Wave 0 |
| SI-02b | Promotion does NOT change `active_version()` until boot/reload; rollback re-points to `previous_version` | unit (default) | `pytest tests/test_version_pin.py` | ❌ Wave 0 |
| SI-03 | Offline proposer mines durable traces, emits `DRAFT` inert proposal, nothing promoted; loop capped | unit (default) | `pytest tests/test_reflective_proposer.py -m "not live"` | ❌ Wave 0 |
| (regression) | Existing pipeline (hash-rebind, refusal, rollback) still green | unit (default) | `pytest tests/test_self_improvement.py` | ✅ exists (11 tests) |

### Sampling Rate
- **Per task commit:** `pytest -q -m "not live"` (must stay green + creds-free).
- **Per wave merge:** full `make test`; run `make test-live` when judge/calibration code changes and creds are available.
- **Phase gate:** full default suite green before `/gsd:verify-work`; `live` lane exercised at least once with creds.

### Wave 0 Gaps
- [ ] `tests/test_eval_harness.py` — SI-01/01b/01c (frozen-item determinism, no-regression gate, creds-free runner)
- [ ] `tests/test_reflective_proposer.py` — SI-03/01a (inertness via stub reflector, held-out isolation, loop cap)
- [ ] `tests/test_ai_bom.py` — SI-02/02a (valid CycloneDX 1.7 JSON, ML component, manifest mapping)
- [ ] `tests/test_version_pin.py` — SI-02b (non-hot proof + rollback re-point proof)
- [ ] `tests/test_judges_live.py` — SI-01d (`@pytest.mark.live`, `live_creds`; order-swap, calibration, Type-I)
- [ ] Possible `tests/conftest.py` fixture: a stub reflector (mirror `_RecordingRouter`) + frozen-item fixtures
- [ ] Dep install: `pip install -e ".[aibom]"` (new extra) into the env running `make test`
- [ ] Possible `migrations/0003_*.sql`: `current_active_version` pointer + baseline-scores storage (if not a JSON column)

## Security Domain

> `security_enforcement` not found as `false` in `.planning/config.json` → treated as enabled. This phase's primary risk surface is **governance integrity** (self-modification), already controlled by Option C.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No new auth surface; live creds via existing `live_creds` |
| V3 Session Management | no | — |
| V4 Access Control | **yes** | Promotion gated by approval ledger + payload-hash rebind (existing); HIGH/CRITICAL never auto-promote |
| V5 Input Validation | **yes** | Pydantic contracts validate proposals/eval results; CycloneDX library validates BOM structure; tenant-scoping on all reads |
| V6 Cryptography | **yes (reuse)** | Payload-hash binding via existing `approvals.payload_hash` — never hand-roll a new hashing scheme |

### Known Threat Patterns for self-evolving agents
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Reward hacking (proposer games the gate) | Tampering | Held-out set distinct from optimization signal + zero-overlap test (D-02, SI-01a) |
| Silent runtime self-modification | Elevation of Privilege | Option C: inert proposals, human-gated non-hot promotion, no runtime mutation (CLAUDE.md §8) |
| Approval replay after artifact mutation | Tampering | Payload-hash rebind in `promote_proposal` (already tested) |
| Position-bias / judge gaming | Tampering | Order-swap + calibration + never sole arbiter at close margins (D-05/D-06) — `live` lane |
| Tenant data leakage in trace mining | Information Disclosure | Tenant-scoped `list_tool_calls`/`list_evaluations` (DUR-02) |
| Promoting unaudited capability | Repudiation | CycloneDX ML-BOM bound to version + 12-month append-only ledger |

## Sources

### Primary (HIGH confidence) — verified in-tree this session
- `.venv/.../langfuse 4.7.1` signatures (`run_experiment`, `get_dataset(version=)`, `Evaluation`, `LocalExperimentItem`) — inspected + executed creds-free.
- `src/agent_mesh/services/self_improvement.py`, `contracts/models.py`, `contracts/enums.py`, `observability.py`, `settings.py`, `services/repository.py`, `tests/test_self_improvement.py`, `tests/conftest.py`, `pyproject.toml`, `Makefile`, `migrations/0002_self_improvement.sql`, `manifests/*.yaml`.
- PyPI: `cyclonedx-python-lib` 11.8.0 (and `langfuse` 4.7.1) via `pip index versions`.
- CycloneDX `schema/__init__.py` (SchemaVersion V1_7) + readthedocs autoapi (`ComponentType.MACHINE_LEARNING_MODEL`, no `model_card`) + GitHub issue #912 (no ModelCard model).

### Secondary (MEDIUM) — pre-settled by the commissioned deep-research report (06-CONTEXT Canonical References)
- GEPA arXiv:2507.19457; reward-hacking OpenReview ikrQWGgxYg + arXiv:2407.04549; position bias arXiv:2406.07791; calibration/Type-I arXiv:2601.20913 + arXiv:2604.03257; MIRAGE-Bench arXiv:2507.21017; CycloneDX ML-BOM cyclonedx.org ECMA-424 v1.7; surveys arXiv:2507.21046 / 2508.07407; DGM arXiv:2505.22954.
- Langfuse experiments docs `langfuse.com/docs/evaluation/experiments/experiments-via-sdk` + changelogs 2025-09-17 / 2025-11-06.

### Tertiary (LOW) — flagged
- Exact `cyclonedx-python-lib` output-API symbols across majors (A2) — confirm against installed version at impl time.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — langfuse runner verified present + creds-free in-tree; cyclonedx version/spec/ML-component verified on PyPI+docs.
- Architecture / seams: HIGH — all five insertion points read directly; ~80% pipeline already exists and tested.
- ML-BOM conformance detail: MEDIUM — ModelCard gap is verified; exact output-API symbols need impl-time confirmation (A2).
- Pitfalls: HIGH — each grounded in a verified repo fact or the settled report.

**Research date:** 2026-06-07
**Valid until:** 2026-07-07 (stable; langfuse and cyclonedx move, re-verify `run_experiment`/output-API on any minor bump)

---

### Plan-sequencing review (06-01..06-05) and dependencies

The 5 ROADMAP stubs are sound. Refinements:

1. **06-01 (harness)** — split internally into (a) creds-free runner+gate (default lane) and (b) `live` wrapper, but keep as one plan. Owns the held-out dataset + frozen-item builder + no-regression gate + `evaluate_proposal` body swap. **Foundation — others depend on it.**
2. **06-02 (proposer + loop)** — depends on 06-01's held-out pool (must consume the *isolated* set for re-validation; must NOT mine it). Owns `reflective_proposer.py` + bounded loop + inertness tests. **Cross-plan invariant with 06-01: held-out isolation (Pattern 3) — assign the zero-overlap test explicitly to one plan.**
3. **06-03 (live judge)** — depends on 06-01 (plugs LLM-judge as `run_evaluators`). Fully `live`-lane. Independent of 06-04/05.
4. **06-04 (ML-BOM)** — independent of 06-01/02/03; depends only on manifests + `AIBOMSnapshot`/`promote_proposal`. Adds the `[aibom]` dep (gate first install behind `checkpoint:human-verify`). Can run in parallel with 06-01/02/03.
5. **06-05 (non-hot wiring + rollback)** — depends on 06-04 only insofar as `promote_proposal` is the integration point; the boot-time loader + rollback re-point are otherwise independent. **Most likely to need migration `0003`** (active-version pointer).

**Suggested wave structure:** Wave A = {06-01, 06-04} (foundations, parallel) → Wave B = {06-02, 06-03, 06-05} (depend on A). **Landmines:** (i) the lane split in 06-01 (must-resolve, resolved above); (ii) the held-out isolation invariant straddling 06-01/06-02 (assign explicitly); (iii) cyclonedx output-API symbols (A2 — confirm at impl); (iv) non-hot loader must NOT copy the call-time `get_settings`/`get_prompt_with_fallback` pattern (Pattern 5).
