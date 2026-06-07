# Phase 6: Self-Improvement (real loop) - Pattern Map

**Mapped:** 2026-06-07
**Files analyzed:** 13 (5 new src modules, 2 modified src modules, 5 new tests, 1 new migration; + pyproject extra + conftest fixture edits)
**Analogs found:** 12 / 13 (two novel halves — CycloneDX generation, LLM-judge scoring — have no in-repo generation analog)

> **Scope grounding:** ~80% of the pipeline already exists (`reflect → evaluate → approve → promote → rollback` with payload-hash rebind, fully tested in `tests/test_self_improvement.py`). Phase 6 is **four targeted insertions** (real gate body, offline proposer, ML-BOM generator, non-hot loader) + a `live` judge lane, not a rebuild. Copy the existing seam shapes; do not re-architect them.

> **Critical correction to RESEARCH.md:** RESEARCH.md repeatedly names the new migration `0003`, but `migrations/0003_tool_call_fields.sql` **already exists** (Phase 4) and is registered in `tests/conftest.py:8` `_MIGRATIONS`. The Phase-6 migration MUST be **`0004_*.sql`**. Propagating "0003" causes a filename collision. See the `0004` row below.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/agent_mesh/services/self_improvement.py` (MODIFY: swap `evaluate_proposal` body; flesh `reflect_on_task`) | service | transform / batch | itself (existing pipeline) + `evaluate_proposal:149` stub | exact (in-place) |
| `src/agent_mesh/services/repository.py` (MODIFY: add active-version read + pointer write) | data-access | CRUD | tenant-scoped `list_evaluations:177` / `get_promotion:192` (read) + `upsert_promotion:187` (write) | exact (mirror existing methods) |
| `src/agent_mesh/services/eval_harness.py` (NEW) | service | batch / transform | `observability.py` Langfuse seed + `self_improvement.evaluate_proposal` | role-match |
| `src/agent_mesh/services/reflective_proposer.py` (NEW) | service (offline meta-agent) | batch / transform | `self_improvement.reflect_on_task:110` + tenant-scoped `repository.list_tool_calls` | exact (seam) |
| `src/agent_mesh/services/ai_bom.py` (NEW) | service / governance generator | transform (manifest → CycloneDX JSON) | `tools/gateway.py:load_tool_pack:56` (manifest read) + `AIBOMSnapshot` model (output target) | role-match (generation half novel) |
| `src/agent_mesh/services/version_pin.py` (NEW) | config / boot loader | request-response (read-once-at-boot) | `observability.py` `_PROCESS_PROVIDER` cache (186–219) | exact (set-once cache) |
| `src/agent_mesh/eval/judges.py` (NEW) | service (live-lane evaluator) | transform / request-response | `observability.py` lazy-optional-dep + `live_creds` gate | role-match (judge logic novel) |
| `migrations/0004_active_version.sql` (NEW) | migration | — | `0002_self_improvement.sql` (CREATE TABLE) or `0003_tool_call_fields.sql` (ADD COLUMN) | exact |
| `tests/test_eval_harness.py` (NEW) | test (default lane) | — | `tests/test_self_improvement.py` | exact |
| `tests/test_reflective_proposer.py` (NEW) | test (default lane) | — | `tests/test_self_improvement.py` + `conftest._RecordingRouter` | exact |
| `tests/test_ai_bom.py` (NEW) | test (default lane) | — | `tests/test_self_improvement.py` schema-export test (236–242) | role-match |
| `tests/test_version_pin.py` (NEW) | test (default lane) | — | `tests/test_self_improvement.py` rollback test (209–233) | exact |
| `tests/test_judges_live.py` (NEW) | test (`live` lane) | — | `tests/test_langfuse_seed_live.py` (`pytestmark = pytest.mark.live`) | exact |

**Cross-cutting edits (not standalone files):**
- `pyproject.toml` — add `aibom = ["cyclonedx-python-lib>=8,<12"]` extra. Analog: `tools`/`aggregators` extras (lines 54–65).
- `tests/conftest.py` — add stub-reflector + frozen-item fixtures; register `0004` in `_MIGRATIONS` (line 8).

---

## Pattern Assignments

### `src/agent_mesh/services/self_improvement.py` (MODIFY — service, transform)

**Analog:** itself. The stub to replace is `evaluate_proposal` (`self_improvement.py:149`); the proposer seam to keep is `reflect_on_task` (`:110`); the ML-BOM link to fill is `promote_proposal`'s `ai_bom_snapshot_id` (`:289`).

**Current stub body to replace** (`:178-194`) — keep the `EvaluationResult` shape, the `repo.upsert_evaluation` + `_set_status` calls, and the `pending`/`can_run=False` branch (`:165-176`) untouched; only swap the *scoring engine*:
```python
checks = deterministic_checks or [{"name": "non_empty_patch", "passed": True}]
passed = bool(proposal.proposed_patch.strip()) and all(c.get("passed") for c in checks)
result = EvaluationResult(
    proposal_id=proposal_id, tenant_id=proposal.tenant_id,
    passed=passed, pending=False, checks=checks,
    summary="passed" if passed else "failed deterministic checks",
)
repo.upsert_evaluation(result)
_set_status(repo, proposal, ProposalStatus.EVALUATION_PASSED if passed else ProposalStatus.EVALUATION_FAILED)
```
**Insertion:** the new body calls into `eval_harness` (runs the experiment + the pure-Python no-regression gate), then maps the gate result onto the SAME `EvaluationResult` / `_set_status` flow. Do NOT change the signature's `can_run`/`pending` contract — `test_pending_evaluation_does_not_pass` (test L190) still gates on it.

**Promotion link to fill** (`promote_proposal:280-291`) — `ai_bom_snapshot_id` is already a passthrough kwarg (`:241`); 06-04 generates the snapshot and 06-05 wires the caller to pass the real id. The `PromotionRecord` construction and the payload-hash rebind (`:274`) stay verbatim.

**Rollback re-point (D-13)** — `rollback_promotion` (`:297-314`) today ONLY flips `rolled_back`/`rollback_reason`. 06-05 extends it to also re-point the active-version pointer to `previous_version` via the new repo write (see `repository.py` below). The `model_copy(update={...})` + `upsert_promotion` shape stays; the active-pointer write is added alongside it.

---

### `src/agent_mesh/services/repository.py` (MODIFY — data-access, CRUD)

**Analog:** the existing tenant-scoped self-improvement repo methods. **No `current_active_version` method exists today** (grep-confirmed), and the only promotion read is `get_promotion(promotion_id)` (`:192`) — there is no tenant-ordered list. SI-02b (D-12/D-13) therefore needs **new repo methods that no existing file provides.**

**Methods to add (mirror across all three layers — Protocol `:51-55`, `InMemoryRepository`, `RepositorySQL`, exactly as the existing promotion methods are):**
- A tenant-scoped **read**: `current_active_version(tenant_id) -> str | None` — the boot loader's source. Copy the read shape from `list_evaluations` (`:177-184`):
```python
# repository.py:177 — the tenant-scoped read shape to mirror
def list_evaluations(self, proposal_id: str, tenant_id: str) -> list[EvaluationResult]:
    return [e for e in self._evaluations.values()
            if e.proposal_id == proposal_id and e.tenant_id == tenant_id]
```
- An active-pointer **write** invoked by promote/rollback. Copy the upsert shape from `upsert_promotion` (`:187-190`).

**Open decision (RESEARCH Q3 — leave to planner):** the pointer can be a dedicated row in the new `0004` table OR derived from the latest non-rolled-back `PromotionRecord.promoted_version` (which would instead require a new tenant-ordered `list_promotions` read). Either way a NEW read method is required. If a new table is chosen, the write also lands here.

---

### `src/agent_mesh/services/eval_harness.py` (NEW — service, batch/transform)

**Analog:** `observability.py` (Langfuse-as-optional, creds-free fallback) for the runner half; `self_improvement.evaluate_proposal` for the EvaluationResult emission.

**Lazy optional-dep + creds-free pattern** (copy from `observability.py:57-63` + `:348-371`): Langfuse runs **creds-free over local data** (verified in RESEARCH). Build a disabled client and still execute locally:
```python
# Mirror observability.get_prompt_with_fallback's lazy-import-and-degrade shape.
from langfuse import Langfuse                 # v4 top-level import (NOT langfuse.callback — DEAD)
from langfuse.experiment import Evaluation
lf = Langfuse()  # no keys -> "disabled": no upload, but run_experiment still executes locally
result = lf.run_experiment(name="si-candidate", data=frozen_items,
                           task=deterministic_task, evaluators=[exact_match])
# result.item_results -> feed the pure-Python no-regression gate below
```

**No-regression gate (pure-Python, the actual promotion-eligibility check):** aggregate AND item-level (aggregate alone hides per-item regressions — D-03). Keep this OUT of `run_experiment`; it must be reproducible/creds-free:
```python
def passes_no_regression(candidate, baseline, *, item_threshold):
    if mean(candidate.scores) < mean(baseline.scores):
        return False, [{"reason": "aggregate_below_baseline"}]
    regressions = [{"item_id": i, "delta": c - b}
                   for i, (c, b) in items_zipped(candidate, baseline)
                   if (b - c) > item_threshold]
    return (not regressions), regressions
```

**Baseline storage (RESEARCH Open-Q2/A3 — leave to planner, but DON'T drop it):** the gate compares against a stored baseline that must be readable creds-free in the default lane. Two options: a committed golden JSON fixture keyed by version, OR durable storage (a new repo read + possibly an extra `0004` column/table). If durable storage is chosen, that is an additional `repository.py` read and may extend `0004` — flag the dependency to the planner.

**Anti-patterns (RESEARCH):** do NOT use `run_experiment` AS the gate; do NOT import `live_creds` here (default lane must stay green); do NOT pin datasets via the private `_dataset_version=` kwarg — use public `get_dataset(name, version=<datetime>)`.

---

### `src/agent_mesh/services/reflective_proposer.py` (NEW — service, offline meta-agent)

**Analog:** `self_improvement.reflect_on_task` (`:110-146`) is the production seam it feeds; tenant-scoped `repository.list_tool_calls(task_id, tenant_id)` is the durable trace source.

**It emits proposals THROUGH the existing inert seam — never a new mutation path:**
```python
def propose_from_traces(repo, task, reflect_fn) -> SelfImprovementProposal:
    evidence = repo.list_tool_calls(task.task_id, task.tenant_id)   # durable, TENANT-SCOPED (DUR-02)
    diff = reflect_fn(evidence)        # live lane: real LLM; default lane: stub returns canned diff
    return si.reflect_on_task(repo, task, proposed_patch=diff, ...)  # -> status=DRAFT, inert
```
`reflect_on_task` already sets `status=ProposalStatus.DRAFT` and binds `patch_hash` at creation (`:138,:144`) — inertness is inherited, not re-implemented.

**Inertness assertion (copy the existing test shape, `test_self_improvement.py:26-40`):** `assert proposal.status == ProposalStatus.DRAFT` and no `PromotionRecord` exists.

**Held-out isolation (cross-plan invariant 06-01/06-02 — anti-reward-hack, D-02):** the proposer mines only the train/dev pool; the gate reads only the held-out pool. Add a zero-overlap test:
```python
def assert_holdout_isolation(train_ids: set[str], holdout_ids: set[str]) -> None:
    assert not (train_ids & holdout_ids), "held-out set leaked into proposer optimization signal"
```

**Bounded loop:** cap iterations (config-driven, not hardcoded — Claude's Discretion) and re-validate on the held-out set each round. NOT wired into the live LangGraph supervisor (D-07, CLAUDE.md bounded-roster) — it is a separated offline module.

---

### `src/agent_mesh/services/ai_bom.py` (NEW — governance generator, transform)

**Analog (manifest-read half):** `tools/gateway.py:load_tool_pack:56-74` — the established `yaml.safe_load(Path(path).read_text())` + per-entry field mapping pattern. Copy it for reading `manifests/deployment.manifest.yaml` + `manifests/tool_pack_manifest.yaml`:
```python
# tools/gateway.py:56 — the manifest-read shape to mirror
def load_tool_pack(path: str | Path) -> list[ToolSpec]:
    data = yaml.safe_load(Path(path).read_text())
    for raw in data.get("tools", []):
        ...
```
**Output target:** the existing `AIBOMSnapshot` model (`contracts/models.py:213-226` — `agents/tools/skills/prompts/model_routes` fields). Persist the CycloneDX JSON and set `PromotionRecord.ai_bom_snapshot_id`.

**Generation half — NO in-repo analog (see No Analog Found).** CycloneDX emission is novel; follow RESEARCH Pattern 6: `ComponentType.MACHINE_LEARNING_MODEL` + `Property` entries (the library has NO `ModelCard` model — issue #912), `SchemaVersion.V1_7`, `make_outputter(...).output_as_string()`. **Confirm exact output-API symbols against the installed version at impl time** (RESEARCH A2). Pure data-model serializer → default lane, no creds.

**Dep-add analog:** add `aibom = ["cyclonedx-python-lib>=8,<12"]` to `pyproject.toml`, mirroring the opt-in `tools`/`aggregators` extras (lines 54–65). Gate the first install behind a `checkpoint:human-verify` (RESEARCH Package Audit `[ASSUMED]`).

---

### `src/agent_mesh/services/version_pin.py` (NEW — boot loader, read-once-at-boot)

**Analog:** `observability.py` `_PROCESS_PROVIDER` module-global cache (`:198-219`) — the existing **"built once… reuses across runs rather than rebuilding per task"** pattern. This IS the non-hot, set-once, never-re-read-mid-run shape (D-12):
```python
# observability.py:214 — the positive analog (set-once module cache)
global _PROCESS_PROVIDER
if _PROCESS_PROVIDER is None:
    _PROCESS_PROVIDER = init_tracing(settings)
```
Mirror it for the active version (the read comes from the new `repository.current_active_version` — see `repository.py` above):
```python
_ACTIVE_VERSION: str | None = None   # module-level cache, set once at boot
def load_active_version_at_boot(repo, tenant_id) -> str:
    global _ACTIVE_VERSION
    _ACTIVE_VERSION = repo.current_active_version(tenant_id)   # read at start/deploy only
    return _ACTIVE_VERSION
def active_version() -> str | None:
    return _ACTIVE_VERSION   # never re-reads the store mid-run
```

**ANTI-PATTERN (do NOT copy this half of `observability.py`):** `get_prompt_with_fallback` (`:348`) and any `get_settings()`-at-call-time read are **call-time** patterns — using them for the active version is effectively hot-swapping and violates D-12 / criterion 5 / CLAUDE.md no-runtime-mutation. The non-hot proof test must show a promotion does NOT change `active_version()` until an explicit `load_active_version_at_boot()` reload.

**Rollback (D-13):** `rollback_promotion` re-points the active pointer to `previous_version` (not merely a status flip — extend the existing `rollback_promotion:297-314`, which today only flips `rolled_back`, via the new repo write). Next `load_active_version_at_boot()` returns the restored version.

---

### `src/agent_mesh/eval/judges.py` (NEW — `live`-lane evaluator)

**Analog (structure/gating):** `observability.py` lazy-optional-dep guards + the `live_creds` fixture (`conftest.py:114-126`). The judge logic itself (order-swap, calibration TPR/FPR, finite-sample Type-I gate) is **novel — no in-repo analog** (see No Analog Found).

**Lane gating:** entirely behind `live_creds`; plugged in as `run_evaluators` only when creds exist. Never imported by the default-lane harness. Never the sole arbiter at close margins (D-05/D-06).

---

### `migrations/0004_active_version.sql` (NEW — migration)

**Analog:** `0002_self_improvement.sql` if the active-version pointer is a **new table** (`CREATE TABLE IF NOT EXISTS`); `0003_tool_call_fields.sql` if it is an **additive column** (`ADD COLUMN IF NOT EXISTS`).

**CREATE-TABLE shape (from `0002`, idempotent + tenant-partitioned + 12-month-audit header):**
```sql
-- Agent Mesh POC — active-version pointer (non-hot promotion wiring, SI-02b).
-- Region: australia-southeast1. Follows 0001/0002/0003 conventions:
--   * Tenant partitioning via tenant_id. Append-only governance. Idempotent (IF NOT EXISTS).
CREATE TABLE IF NOT EXISTS self_improvement_active_version (
    tenant_id        TEXT PRIMARY KEY,
    active_version   TEXT NOT NULL,
    promotion_id     TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
**ADD-COLUMN shape (from `0003`):** `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ... DEFAULT ...` (every column safe-defaulted so historical rows stay valid).

**Integration point (REQUIRED):** register `"0004_active_version.sql"` in `tests/conftest.py:8` `_MIGRATIONS`, else SQL-backed tests never apply it.

---

### Test files (all default lane except `test_judges_live.py`)

**Analog for ALL:** `tests/test_self_improvement.py` — the `repo` fixture, the `_task(repo)` helper (L14-23), `si.*` calls, and the `with pytest.raises(si.PromotionRefused):` refusal shape.

- **`test_version_pin.py`** — copy the rollback flow from `test_rollback_marks_promotion_and_proposal` (L209-233): evaluate → open approval → APPROVED decision → promote → assert. Add the non-hot proof (promote does NOT change `active_version()` until reload) and rollback re-point proof.
- **`test_ai_bom.py`** — copy the schema-validity assertion shape from `test_self_improvement_models_registered_for_schema_export` (L236-242); assert valid CycloneDX 1.7 JSON, an ML component, and manifest-field mapping.
- **`test_reflective_proposer.py`** — copy the inert-draft assertion from `test_reflection_hook_creates_inert_draft_proposal` (L26-40); add held-out-isolation + loop-cap. Use the stub reflector (below).
- **`test_judges_live.py`** — module-level `pytestmark = pytest.mark.live` exactly like `tests/test_langfuse_seed_live.py:23`; consume `live_creds`.

---

## Shared Patterns

### Tenant-scoping on every repo read (DUR-02)
**Source:** `repository.py` — `list_tool_calls(task_id, tenant_id)` (`:132`), `list_evaluations(proposal_id, tenant_id)` (`:177`).
**Apply to:** the proposer trace-mining, the eval baseline read, the new `version_pin`/`repository.current_active_version(tenant_id)`. Never read a single entity without the tenant filter.

### Payload-hash approval binding (reuse, never re-implement)
**Source:** `self_improvement.promote_proposal:274` → `approvals.is_approved(record, {"proposed_patch": proposal.proposed_patch})`; bound at creation in `reflect_on_task:144`.
**Apply to:** any new write-class change (a prompt/tool/route change IS a write — CLAUDE.md §8). Proven by `test_promotion_refused_if_artifact_mutated_after_approval` (L165-187). Do not introduce a second hashing scheme.

### `live`-lane double gate (creds-free default suite)
**Source:** `pyproject.toml:91-92` `live` marker; `conftest.py:114-126` `live_creds`; `Makefile:31-35` `test` / `test-live`.
**Apply to:** `eval/judges.py`, `test_judges_live.py`, any real-model task fn or GEPA reflection LLM call. The default suite (`pytest -m "not live"`) must import none of it.

### Stub-double for creds-free determinism
**Source:** `conftest._RecordingRouter` (`:129-170`) — a recording fake that returns a deterministic response with no network/creds.
**Apply to:** a new `stub_reflector` fixture (records calls, returns a canned diff) so the proposer's inertness/plumbing is proven without a live LLM. Add alongside `_RecordingRouter` in `conftest.py`.

### Optional-dep lazy import + degrade
**Source:** `observability.py:57-63` (`langfuse_available`), `:348-371` (degrade to local default).
**Apply to:** `cyclonedx` import in `ai_bom.py`, `langfuse` import in `eval_harness.py` — lazy, feature-gated, never crash the import of a default-lane module.

### Repository method mirrored across all three layers
**Source:** every existing repo method appears in the `Protocol` (`:38-63`), `InMemoryRepository`, AND `RepositorySQL`. E.g. `list_evaluations:51-53` (Protocol) / `:177-184` (in-memory).
**Apply to:** the new `current_active_version` read (+ active-pointer write) — add to all three layers, never just one.

### Idempotent, tenant-partitioned, audit-headered migration
**Source:** `0002_self_improvement.sql` header (L1-16) + `IF NOT EXISTS` everywhere; `0003` ADD-COLUMN idempotency.
**Apply to:** `0004_active_version.sql`.

---

## No Analog Found

| File / Half | Role | Data Flow | Reason | Planner action |
|------|------|-----------|--------|----------------|
| `ai_bom.py` — CycloneDX *generation* half | governance generator | transform | `AIBOMSnapshot` is the output target, not a generation pattern; no in-repo CycloneDX/SBOM emitter exists | Follow RESEARCH Pattern 6 + confirm output-API symbols at impl (A2); gate `[aibom]` install behind `checkpoint:human-verify` |
| `eval/judges.py` — LLM-judge *scoring* logic | live-lane evaluator | transform | No in-repo LLM-as-judge, position-bias, calibration, or Type-I-gate code exists | Follow RESEARCH D-05/D-06 (order-swap, TPR/FPR calibration, finite-sample gate); `live` lane only; numerics are config-driven (Claude's Discretion) |

> The *structural* halves of both files DO have analogs (manifest read → `gateway.load_tool_pack`; live-gating → `observability` + `live_creds`). Only the domain-specific generation/judgement logic is genuinely new.

---

## Metadata

**Analog search scope:** `src/agent_mesh/services/`, `src/agent_mesh/`, `src/agent_mesh/tools/`, `tests/`, `migrations/`, `manifests/`, `pyproject.toml`, `Makefile`.
**Files scanned (read in full or targeted):** `self_improvement.py`, `contracts/models.py` (200-369), `observability.py`, `migrations/0002`, `migrations/0003`, `tests/test_self_improvement.py`, `tests/conftest.py`, `tools/gateway.py` (50-94), `pyproject.toml` (18-77); grep-grounded: repository read methods (`current_active_version` confirmed ABSENT), `pytest.mark.live` usages, yaml manifest loaders.
**Pattern extraction date:** 2026-06-07
