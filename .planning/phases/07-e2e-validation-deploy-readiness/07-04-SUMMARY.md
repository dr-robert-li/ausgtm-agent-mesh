---
phase: 07-e2e-validation-deploy-readiness
plan: 04
subsystem: testing
tags: [deploy-readiness, gcloud, wrangler, idempotency, pytest, subprocess, yaml, manifest]

# Dependency graph
requires:
  - phase: 07-e2e-validation-deploy-readiness
    provides: deploy scripts (gcp_bootstrap.sh, gcp_deploy_core.sh, cf_deploy_ai_gateway_worker.sh), deployment + tool-pack manifests, schemas/
provides:
  - PATH-shim subprocess harness proving gcloud/wrangler reuse-vs-create idempotency LOGIC locally (no live cloud)
  - Always-on bash -n syntax floor over scripts/*.sh + loud-skip shellcheck lint leg
  - Pub/Sub --dead-letter-topic + --max-delivery-attempts=5 asserted as E2E-03 job-retry deploy-config evidence
  - New manifest-consistency validator (env-var contract, schema coverage, required-stack) with loud-skip wrangler --dry-run
affects: [deploy, deployment-runbook, ci]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Catch-all fake CLI shim on subprocess-scoped PATH (default exit-0 reuse; narrow per-test SHIM_ABSENT_PATTERN keyed on describe verbs)"
    - "Loud skip-if-absent for optional dev tools (shellcheck/wrangler) — named gap, never a silent cap"
    - "File-relative (__file__ parents[2]) manifest/script/schema resolution, cwd-independent"

key-files:
  created:
    - tests/deploy/__init__.py
    - tests/deploy/bin/gcloud
    - tests/deploy/bin/wrangler
    - tests/deploy/test_gcloud_idempotency.py
    - tests/deploy/test_manifest_consistency.py
  modified: []

key-decisions:
  - "Shim defaults to exit-0 (reuse) and 'absent' is a narrow per-test describe-verb pattern — required so the linear set -euo pipefail scripts run to completion instead of aborting mid-run"
  - "D-11 resolved as a NEW validator (not an export_schemas extension) — export_schemas only does Pydantic->JSON-Schema and never reads YAML manifests"
  - "Schema-coverage checks only tools that declare input/output schema refs; schema-less aggregator tools (composio/nango) are exempt by design (D-04)"
  - "Tool integration styles checked against the 5-element KNOWN set, NOT against the manifest's declared list (composio_aggregator is used by tools but intentionally absent from the declared list)"

patterns-established:
  - "DEP idempotency proof: subprocess.run with prepended-PATH shim dir scoped to env; assert describe->|| create short-circuit both directions"
  - "Manifest consistency: explicit ENV_VAR->manifest-field map (avoids :=-default false orphans) with bidirectional no-orphan assertion"

requirements-completed: [DEP-01, DEP-02]

# Metrics
duration: 12min
completed: 2026-06-07
---

# Phase 7 Plan 04: Deploy-Readiness Idempotency & Manifest-Consistency Summary

**PATH-shim subprocess harness proves the gcloud/wrangler reuse-vs-create idempotency logic and a new YAML-manifest validator proves deployment/tool-pack/script/schema consistency — all locally, with no live cloud provisioning.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-07T22:22Z
- **Completed:** 2026-06-07T22:34Z
- **Tasks:** 2
- **Files created:** 5

## Accomplishments
- DEP-01: a catch-all fake `gcloud`/`wrangler` on a subprocess-scoped PATH drives the real deploy scripts and proves the reuse-vs-create idempotency logic for the Artifact Registry, Pub/Sub worker-subscription, service-account, Cloud SQL-instance, and `deploy_job` branches — asserting BOTH reuse (no `create` when a resource exists) AND create (when absent).
- An always-on `bash -n` syntax floor over `scripts/*.sh` (never skip-gated) plus a `shellcheck` lint leg that skips loudly when the tool is absent.
- The Pub/Sub `--dead-letter-topic` + `--max-delivery-attempts=5` worker-subscription wiring is asserted as the literal E2E-03 "job retry" (redelivery) deploy-config evidence (cross-ref plan 07-03).
- DEP-02 / D-11: a new dedicated validator reads the YAML deployment + tool-pack manifests and asserts (1) the env-var contract maps 1:1 to manifest fields with no orphan either side, (2) every declared tool input/output schema ref resolves on disk and all integration styles are within the known set, and (3) the required stack (langchain+langgraph+deepagents / langfuse / langsmith optional-only).
- A `wrangler --dry-run` leg that runs when installed else skips loudly.

## Task Commits

1. **Task 1: tests/deploy package + catch-all shims + idempotency-logic harness (DEP-01)** - `30b4697` (test)
2. **Task 2: manifest-consistency validator + wrangler dry-run loud-skip leg (DEP-02 / D-11)** - `aa9f26c` (test)

## Files Created/Modified
- `tests/deploy/__init__.py` - package marker for the deploy harness
- `tests/deploy/bin/gcloud` - catch-all fake gcloud (records argv to `$SHIM_LOG`, default exit-0 reuse, narrow `$SHIM_ABSENT_PATTERN` absent; record-and-exit only, no delegation)
- `tests/deploy/bin/wrangler` - catch-all fake wrangler (same contract)
- `tests/deploy/test_gcloud_idempotency.py` - PATH-shim subprocess harness + bash -n floor + shellcheck loud-skip + Pub/Sub redelivery config assertion (DEP-01)
- `tests/deploy/test_manifest_consistency.py` - new env-var/schema/required-stack validator + wrangler dry-run loud-skip (DEP-02 / D-11)

## Decisions Made
- **Default-0 shim, narrow absent.** The deploy scripts are linear `set -euo pipefail`; a broad "absent" switch (or a substring matching both `describe` and `create`) would abort the script mid-run and skip later assertions. The shim therefore exits 0 by default (reuse) and only flips a single targeted `describe` probe via a per-test pattern. `projects describe` is left always-0 to avoid the `CREATE_PROJECT=false` early exit.
- **D-11 = new validator.** Documented in the module docstring: `export_schemas` only emits Pydantic contract schemas and never touches the YAML manifests, so a new module (importing none of the export machinery) is the correct home for manifest consistency.
- **Explicit 13-var env map.** Only `PROJECT_ID` and `CLOUDFLARE_ACCOUNT_ID` use the strict `:?` guard; everything else uses `:=` defaults, so a generic `${VAR...}` regex would produce false orphans (`IMAGE_TAG`, `SQL_TIER`, ...). The explicit map enumerated by the plan is the contract.

## Deviations from Plan

None - plan executed exactly as written. No bugs, missing-critical, or blocking issues encountered; no architectural changes required.

## Issues Encountered
- The dev machine has a real `gcloud` on PATH (`/Users/robertli/google-cloud-sdk/bin/gcloud`) and lacks `shellcheck`/`wrangler`. This is exactly why the shim must be catch-all and prepended to a subprocess-scoped PATH (so the fake wins, T-07-11) and why the shellcheck/wrangler legs are the actual default-lane loud-skip path (D-10). Both handled as designed.
- `ruff`/`pytest` live in the main-repo `.venv` (`/Users/robertli/Desktop/consulting/ausgtm-agent-mesh/.venv/bin/python`), not on the bare `python3`; verification ran through that interpreter. `pyproject` `pythonpath=["src"]` resolves to the worktree rootdir, so imports work normally.

## Verification Evidence
- `tests/deploy/` (not live): **19 passed, 2 skipped** (shellcheck + wrangler loud skips, each naming the gap).
- `test_gcloud_idempotency.py`: 13 passed, 1 skipped; `ruff check` clean.
- `test_manifest_consistency.py`: 6 passed, 1 skipped; `ruff check` clean.
- Whole suite `pytest -q -m "not live"`: **300 passed, 8 skipped, 21 deselected** — `make test` stays green with the new package.
- `bash -n` passes on all three `scripts/*.sh` (the non-skip-gated floor).
- No real cloud call: the `$SHIM_LOG` is the only record of any gcloud/wrangler invocation.

## Known Stubs
None. The fake shims are intentional test doubles (not product stubs); they record-and-exit and never delegate to a real binary (closing T-07-10).

## User Setup Required
None - no external service configuration required. The harness is fully offline; `shellcheck`/`wrangler` are optional (loud-skipped when absent).

## Next Phase Readiness
- DEP-01 + DEP-02 are proven locally, completing the deploy-ready ceiling (ROADMAP SC-4) without live provisioning.
- The idempotency the scripts claim by design is now PROVEN by test, and the manifest/script/schema contract is guarded against silent drift.
- Optional follow-ups for a CI runner that has the tools installed: the shellcheck and `wrangler --dry-run` legs will execute (rather than skip) automatically — no code change needed.

## Self-Check: PASSED

All created files verified present on disk; both task commits (`30b4697`, `aa9f26c`) verified in git history.

---
*Phase: 07-e2e-validation-deploy-readiness*
*Completed: 2026-06-07*
