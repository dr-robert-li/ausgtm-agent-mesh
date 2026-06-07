---
phase: 06-self-improvement
plan: 01
subsystem: database
tags: [postgres, pgvector, repository, cyclonedx, ai-bom, self-improvement, tenant-scoping]

# Dependency graph
requires:
  - phase: 01-durable-core-approval-security
    provides: repository.py three-layer pattern (Protocol/InMemory/SQL), migration conventions, conftest migration applier
  - phase: 03-model-gateway-observability
    provides: conftest _RecordingRouter recording-fake pattern (mirrored for stub_reflector)
provides:
  - migration 0004_active_version.sql (self_improvement_active_version pointer + ai_bom_snapshots tables)
  - repository.current_active_version / set_active_version (SI-02b active-version pointer)
  - repository.upsert_ai_bom / get_ai_bom (SI-02 AI-BOM persistence, consumed by 06-05)
  - conftest stub_reflector + frozen_holdout_items fixtures (consumed by 06-02/06-03)
  - [aibom] pyproject extra (cyclonedx-python-lib) vetted + installed
  - confirmed cyclonedx V1_7 output-API import paths for 06-05
affects: [06-02, 06-03, 06-05, 06-06]

# Tech tracking
tech-stack:
  added: [cyclonedx-python-lib>=8 <12 (installed 11.8.0, [aibom] extra)]
  patterns: [tenant-scoped repo read returning None on tenant mismatch, recording-fake reflector fixture, frozen held-out experiment items]

key-files:
  created:
    - migrations/0004_active_version.sql
    - tests/test_active_version_repo.py
    - .planning/phases/06-self-improvement/deferred-items.md
  modified:
    - src/agent_mesh/services/repository.py
    - tests/conftest.py
    - pyproject.toml

key-decisions:
  - "Active-version pointer is a dedicated 0004 row (self_improvement_active_version), not derived from PromotionRecord — matches PATTERNS RESEARCH Q3 option A, write lands in repository.set_active_version"
  - "upsert_ai_bom uses ON CONFLICT (snapshot_id) DO NOTHING (snapshots are immutable point-in-time bundles); InMemory mirrors with setdefault"
  - "get_ai_bom returns None on tenant mismatch (not raise) — mirrors current_active_version tenant scoping for a uniform DUR-02 read contract"

patterns-established:
  - "Tenant-scoped single-entity read returns None for a non-owning tenant (DUR-02), asserted by a negative test"
  - "Recording-fake fixture (stub_reflector) mirrors _RecordingRouter: records calls, returns a canned deterministic result, no network/creds"

requirements-completed: [SI-02b]

# Metrics
duration: 31min
completed: 2026-06-07
---

# Phase 6 Plan 01: Self-Improvement Shared-File Foundations Summary

**Migration 0004 (active-version pointer + ai_bom_snapshots), tenant-scoped repository active-version + AI-BOM read/write across all three layers, downstream conftest fixtures, and the vetted cyclonedx [aibom] extra — dissolving the shared-file collision surface for waves 2-3.**

## Performance

- **Duration:** ~31 min
- **Started:** 2026-06-07T21:06:28+10:00 (first commit — [aibom] extra)
- **Completed:** 2026-06-07T21:36:47+10:00 (GREEN repo commit)
- **Tasks:** 3 (1 checkpoint, 2 auto/tdd)
- **Files modified:** 6

## Accomplishments
- New `migrations/0004_active_version.sql`: two idempotent, tenant-partitioned tables — `self_improvement_active_version` (per-tenant active-version pointer, SI-02b) and `ai_bom_snapshots` (SI-02 persistence target for 06-05), registered in conftest `_MIGRATIONS` + `_TABLES`.
- `repository.py`: `current_active_version` / `set_active_version` and `upsert_ai_bom` / `get_ai_bom` on the `Repository` Protocol, `InMemoryRepository`, AND `RepositorySQL` (3 layers each, grep-confirmed), with tenant-scoped reads (DUR-02) and a `_AI_BOM_COLS` + `_row_to_ai_bom` rehydration helper mirroring the promotion shapes.
- `conftest.py`: `stub_reflector` (recording fake) and `frozen_holdout_items` (LocalExperimentItem-shaped) fixtures for downstream 06-02/06-03.
- `[aibom]` extra vetted on pypi.org (OWASP CycloneDX reference lib, NOT the `cyclonedx-bom` CLI) and installed (cyclonedx-python-lib 11.8.0) into the make-test `.venv`.

## cyclonedx output-API import paths (resolves RESEARCH A2 — for 06-05)

Confirmed against installed cyclonedx-python-lib **11.8.0** (creds-free, all probes exit 0):

```python
import cyclonedx.model.bom                                    # BOM model
from cyclonedx.output import make_outputter                   # serializer factory
from cyclonedx.schema import SchemaVersion, OutputFormat      # SchemaVersion.V1_7 ; OutputFormat.JSON
```

`SchemaVersion.V1_7` and `OutputFormat.JSON` both exist in 11.8.0.

## Repository signatures (for 06-05 / 06-06 to consume)

```python
def current_active_version(self, tenant_id: str) -> str | None: ...
def set_active_version(self, tenant_id: str, version: str, promotion_id: str | None = None) -> None: ...
def upsert_ai_bom(self, snapshot: AIBOMSnapshot) -> AIBOMSnapshot: ...
def get_ai_bom(self, snapshot_id: str, tenant_id: str) -> AIBOMSnapshot | None: ...
```

## Task Commits

1. **Task 1: Vet + install cyclonedx-python-lib (supply-chain gate T-06-SC)** — `8da44f0` (chore: [aibom] extra declared, committed during plan-check phase) + human-approved install of cyclonedx-python-lib 11.8.0 into `.venv` with import + V1_7 probes passing (12-month audit sign-off recorded by the requester).
2. **Task 2: migration 0004 + conftest registration** — `9011377` (feat)
3. **Task 3 (TDD):**
   - RED — `5cd8d2a` (test: 8 failing tests, all AttributeError)
   - GREEN — `5effe09` (feat: methods across 3 layers + conftest fixtures)

**Plan metadata:** _this commit_ (docs: complete plan)

## Files Created/Modified
- `migrations/0004_active_version.sql` — active-version pointer + ai_bom_snapshots tables (idempotent, tenant-partitioned, JSONB rich fields).
- `src/agent_mesh/services/repository.py` — active-version + AI-BOM methods on all three layers; `AIBOMSnapshot` import; `_AI_BOM_COLS` + `_row_to_ai_bom`.
- `tests/conftest.py` — 0004 registration in `_MIGRATIONS`/`_TABLES`; `stub_reflector` + `frozen_holdout_items` fixtures.
- `tests/test_active_version_repo.py` — 8 default-lane tests (active-version + AI-BOM, incl. tenant-isolation negatives).
- `pyproject.toml` — `[aibom]` extra (declared in prior plan-check commit; install executed this plan).
- `.planning/phases/06-self-improvement/deferred-items.md` — logged pre-existing out-of-scope lint.

## Decisions Made
- Active-version pointer is a dedicated table row (option A from RESEARCH Q3), so both the read and the write live in `repository.py`; no `list_promotions` derivation needed.
- `upsert_ai_bom` is first-write-wins (`ON CONFLICT DO NOTHING` / `setdefault`): an AI-BOM snapshot is an immutable point-in-time bundle.
- `get_ai_bom` returns `None` on tenant mismatch rather than raising, matching `current_active_version`'s uniform DUR-02 read contract.

## Deviations from Plan
None - plan executed exactly as written. (The `[aibom]` extra declaration in `pyproject.toml` was already committed during the plan-check phase as `8da44f0`; this plan executed the human-gated install + probes per Task 1.)

## Issues Encountered
- A single ruff `I001` import-sort nit in the new test file was auto-fixed with `ruff --fix` before the GREEN commit.
- Two pre-existing E501 lint errors in `tests/test_calcom_adapter.py` (Phase 05-04, commit b1c7c03) are out of scope — logged to `deferred-items.md`, not fixed.
- The recurring `Failed to export span batch code: 401` log line is a creds-free Langfuse OTLP background attempt, not a test failure (suite is green).

## User Setup Required
None - no external service configuration required. The `[aibom]` install was completed into the make-test `.venv` this plan.

## Next Phase Readiness
- Shared-file foundations landed: 06-02..06-06 own zero overlapping files in `repository.py` / `conftest.py` / `migrations/` / `pyproject.toml` and can run parallel-safe per wave plan.
- SQL-layer methods + 0004 DDL are inspection-validated only in the default lane (the `pg_dsn`/`TEST_DATABASE_URL` SQL suite is opt-in and not run here); they mirror the proven promotion shapes exactly.
- cyclonedx V1_7 output API confirmed and recorded for 06-05's ML-BOM generation.

## Self-Check: PASSED

All created/modified files exist on disk (migration 0004, test_active_version_repo.py, repository.py, conftest.py, pyproject.toml, this SUMMARY, deferred-items.md). All task commits present in git log (8da44f0, 9011377, 5cd8d2a, 5effe09).

---
*Phase: 06-self-improvement*
*Completed: 2026-06-07*
