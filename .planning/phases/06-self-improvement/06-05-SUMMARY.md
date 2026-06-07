---
phase: 06-self-improvement
plan: 05
subsystem: governance
tags: [cyclonedx, ml-bom, ai-bom, self-improvement, si-02, si-02a, manifests]

# Dependency graph
requires:
  - phase: 06-self-improvement
    provides: "repository.upsert_ai_bom / get_ai_bom (06-01), [aibom] extra + confirmed cyclonedx V1_7 output-API import paths"
provides:
  - "services/ai_bom.generate_ml_bom(...) -> snapshot_id (SI-02 AI-BOM-on-promotion entry point for 06-06)"
  - "services/ai_bom._build_ml_bom_json(...) -> CycloneDX 1.7 JSON string (SI-02a conformance artifact)"
  - "services/ai_bom.cyclonedx_available() feature gate"
affects: [06-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "lazy/feature-gated optional-dep import mirroring observability.langfuse_available (cyclonedx_available)"
    - "pure builder (_build_ml_bom_json -> str) separated from the persisting entry point (generate_ml_bom -> snapshot_id)"
    - "ML metadata carried as namespaced agentmesh:* CycloneDX Property entries (ModelCard gap #912 workaround)"

key-files:
  created:
    - src/agent_mesh/services/ai_bom.py
    - tests/test_ai_bom.py
  modified: []

key-decisions:
  - "Split a pure _build_ml_bom_json(...) -> CycloneDX JSON string from generate_ml_bom(...) -> snapshot_id, reconciling the plan's `-> str` (returns id, 06-06 needs it for PromotionRecord.ai_bom_snapshot_id) with acceptance criterion #1 (test parses the JSON + asserts specVersion 1.7). AIBOMSnapshot has no free-form JSON column, so the structured manifest-sourced fields are persisted; the serialized CycloneDX string is the validated test artifact."
  - "ML metadata (prompts/dataset_version/eval_result_id/model_route_profile/previous_version) carried as namespaced agentmesh:* Property entries on a single machine-learning-model component — cyclonedx-python-lib has NO ModelCard (#912); D-11 keep-conformance-pragmatic."
  - "prompts derived from the deployment manifest's model_routes.profiles (the closest versioned route bundle; the POC manifest carries no per-agent prompt text)."
  - "tool components emitted as ComponentType.APPLICATION (one per tool-pack tool) with provider/category/integration_style/approval_required as properties."

requirements-completed: [SI-02, SI-02a]

# Metrics
duration: ~10min
completed: 2026-06-07
---

# Phase 6 Plan 05: CycloneDX ML-BOM Generator Summary

**A creds-free `generate_ml_bom` reads the deployment + tool-pack manifests, emits a valid CycloneDX (ECMA-424) v1.7 ML-BOM with one `machine-learning-model` component carrying promoted-bundle metadata as namespaced `Property` entries plus one component per approved tool, persists a structured `AIBOMSnapshot`, and returns its `snapshot_id` to fill `PromotionRecord.ai_bom_snapshot_id` (SI-02 / SI-02a).**

## Performance
- **Duration:** ~10 min
- **Tasks:** 1 (TDD: RED -> GREEN, no REFACTOR needed)
- **Files created:** 2

## Accomplishments
- `src/agent_mesh/services/ai_bom.py`:
  - `_build_ml_bom_json(*, promoted_version, previous_version, dataset_version, evaluation_id, tenant_id, client_slug, route_profile, deployment_manifest_path=..., tool_pack_manifest_path=...) -> str` — pure manifest -> CycloneDX 1.7 JSON transform. One `machine-learning-model` component (version = `promoted_version`) carries prompts / dataset_version / eval_result_id / model_route_profile / previous_version / tenant_id / client_slug as `agentmesh:*` `Property` entries; each tool-pack tool becomes a component. Serialized via `make_outputter(bom, OutputFormat.JSON, SchemaVersion.V1_7).output_as_string()`.
  - `generate_ml_bom(repo, *, <same kwargs>) -> str` — builds (validates) the CycloneDX document, persists a structured `AIBOMSnapshot` (manifest-sourced agents/tools/skills/prompts/model_routes) via `repo.upsert_ai_bom`, returns `snapshot_id`.
  - `cyclonedx_available()` feature gate; the `cyclonedx` import is lazy + feature-gated (mirrors `observability.langfuse_available`) so the module imports without the `[aibom]` extra.
- `tests/test_ai_bom.py` — 6 default-lane tests: valid CycloneDX 1.7 JSON, exactly one ML component (version `v2`), property-mapped ML metadata, tool components mapped from the manifest, persistence round-trip via `repo.get_ai_bom`, and tenant-scoped persistence negative.

## generate_ml_bom signature (for 06-06 promote_proposal wiring)

```python
def generate_ml_bom(
    repo,
    *,
    promoted_version: str,
    previous_version: str | None,
    dataset_version: str | None,
    evaluation_id: str | None,
    tenant_id: str,
    client_slug: str,
    route_profile: str | None,
    deployment_manifest_path: str = "manifests/deployment.manifest.yaml",
    tool_pack_manifest_path: str = "manifests/tool_pack_manifest.yaml",
) -> str:  # returns the new AIBOMSnapshot.snapshot_id
    ...
```

The two manifest paths default to the fixed repo locations, so the 06-06 call site need not source them. Pass the returned id into `PromotionRecord.ai_bom_snapshot_id`.

## Task Commits
1. **Task 1 (TDD):**
   - RED — `fc58358` (test: 6 failing tests, `ModuleNotFoundError: agent_mesh.services.ai_bom`)
   - GREEN — `370516c` (feat: generator + AIBOMSnapshot persistence)

**Plan metadata:** _this commit_ (docs: complete plan)

## Verification
- `tests/test_ai_bom.py`: 6 passed (default lane, creds-free).
- Full suite: **261 passed, 6 skipped** (16 deselected live), 2 deprecation warnings.
  - The `Failed to export span batch code: 401` log line is the known creds-free Langfuse OTLP background attempt (carried from Phase 06-01), not a test failure.
- `ruff check` on both new files: clean.
- `grep -v '^#' src/agent_mesh/services/ai_bom.py | grep -c live_creds` == **0**; no network call (pure `yaml.safe_load` manifest read + in-process CycloneDX serialization).
- Verification interpreter: main-repo `.venv` (cyclonedx 11.8.0) with `PYTHONPATH=src` so imports resolve against the **worktree** `src` (confirmed `agent_mesh.services.repository.__file__` points into the worktree).

## Threat-model coverage
- **T-06-14 (Repudiation):** ML-BOM bound to `promoted_version`, persisted as an immutable `AIBOMSnapshot` (06-01 `upsert_ai_bom` is first-write-wins), id linkable from `PromotionRecord`.
- **T-06-15 (Tampering / invalid BOM):** cyclonedx-python-lib guarantees a valid V1_7 structure; the test parses the JSON and asserts `specVersion == "1.7"` + the ML component.
- **T-06-SC2 (supply chain):** cyclonedx import uses the dep vetted + installed behind the 06-01 blocking-human checkpoint; confirmed import paths reused from the 06-01 SUMMARY.

## Deviations from Plan
**[Reconciliation — not a code deviation] Pure builder split.** The plan's signature says `generate_ml_bom(...) -> str` (returns `snapshot_id`) while acceptance criterion #1 says the test parses the returned JSON for `specVersion 1.7`, and `AIBOMSnapshot` has no JSON column. These cannot all describe one return value. Per the plan's own action note ("The CycloneDX V1_7 JSON string is the function's validated output (asserted by the test); the persisted AIBOMSnapshot is the durable audit record"), I factored a pure `_build_ml_bom_json(...) -> str` (the JSON the test asserts against) called by `generate_ml_bom(...) -> str` (persists the structured snapshot, returns the id). This satisfies the exact public signature 06-06 calls AND every acceptance criterion. No scope or behavior change.

## Known Stubs
None. The generator is a complete pure transform over the shipped manifests. (`prompts` are derived from `model_routes.profiles` because the POC deployment manifest carries no per-agent prompt text — documented decision, not a stub; a richer prompt inventory is a future-manifest concern, not a 06-05 gap.)

## Self-Check: PASSED
- `src/agent_mesh/services/ai_bom.py` — exists on disk.
- `tests/test_ai_bom.py` — exists on disk.
- Commits present in git log: `fc58358` (RED), `370516c` (GREEN).

---
*Phase: 06-self-improvement*
*Completed: 2026-06-07*
