# Phase 7: E2E Validation & Deploy-Readiness - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-08
**Phase:** 7-E2E Validation & Deploy-Readiness
**Areas discussed:** E2E realism & lane, Harness substrate & durability, Failure-mode E2E (E2E-03), Deploy mock strategy (DEP-01/02), Live-lane safety posture

---

## E2E realism & lane

| Option | Description | Selected |
|--------|-------------|----------|
| Split: deterministic default + thin live opt-in | Full chain creds-free in default lane; real seams (Slack sig / SaaS write / model) in opt-in `live` variant | ✓ |
| Deterministic default only | No live E2E variant; real-provider exercise stays in P4/P5 per-adapter live lanes | |
| Live-first | Primary E2E proof requires real creds (breaks creds-free default / deploy-ready scope) | |

**User's choice:** Deterministic default + live E2E to match real (opt-in).
**Notes:** Consistent real-validation lean — prove the assembled chain for real when creds present, keep CI green/creds-free by default.

---

## Harness substrate & durability

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated tests/e2e/, real-PG checkpointer for E2E-02 | New suite via FastAPI TestClient; E2E-02 rides TEST_DATABASE_URL-gated Postgres restart-resume, sqlite fallback | ✓ |
| Dedicated tests/e2e/, in-memory/sqlite only | New suite but E2E-02 uses sqlite/in-memory (no real PG durability) | |
| Extend smoke.py | Grow existing in-memory smoke harness (weakest durability signal) | |

**User's choice:** Dedicated tests/e2e/, real-PG checkpointer for E2E-02.
**Notes:** Avoids hiding the durability SPOF behind an in-memory store; reuses the existing drop-then-reopen restart proof.

---

## Failure-mode E2E (E2E-03)

| Option | Description | Selected |
|--------|-------------|----------|
| One combined run, reuse existing seams deterministically | Single task: fallback → retry → budget-halt in sequence; assert transitions + budget_halt event + FAILED terminal | (basis) |
| Three separately-asserted stages | Each failure mode in its own test (cleaner isolation, doesn't prove composition) | |
| Combined run + live variant | Deterministic combined run + opt-in live variant with real model fallback | ✓ |

**User's choice:** Combined run + live variant.
**Notes:** "Together" SC honoured by the single combined run; live variant adds a real-model fallback + real budget-halt. Ordering forced by seam semantics (fallback/retry succeed mid-run, then budget exhausts → halt).

---

## Deploy mock strategy (DEP-01/02)

| Option | Description | Selected |
|--------|-------------|----------|
| PATH-shim fake gcloud/wrangler; shellcheck/dry-run skip-if-absent (loud) | Fake binary on PATH records describe→create branch decisions; pytest asserts reuse-vs-create; linters SKIP loudly when absent | ✓ |
| Python subprocess harness asserting emitted calls | Pure-python harness with stubbed gcloud; no bash-shim | |
| bats + hard tool deps | Bash-native bats; shellcheck/wrangler required (non-portable) | |

**User's choice:** PATH-shim fake gcloud/wrangler; shellcheck/dry-run skip-if-absent (loud).
**Notes:** Portable default lane, idempotency logic still proven; loud SKIP avoids a silent coverage gap.

---

## Live-lane safety posture (forced by the live-variant choices)

| Question | Option | Selected |
|----------|--------|----------|
| E2E-01 live write | Real draft/sandbox write only (HubSpot sandbox deal / GWS Drive draft) through gate+sandbox | ✓ |
| E2E-01 live write | Real production-grade committed write | |
| E2E-01 live write | Mock the adapter even in live variant | |
| E2E-03 live spend | Tiny cents-cap budget + cheapest models, real halt for ~pennies | ✓ |
| E2E-03 live spend | No special cap (use $50 budget) | |
| E2E-03 live spend | Keep budget-halt deterministic-only | |

**User's choice:** Real draft/sandbox write only; tiny cents-cap budget + cheapest models.
**Notes:** Real chain proven while keeping blast radius reversible and spend bounded — controllability over maximal realism.

---

## Claude's Discretion

- Exact `tests/e2e/` module layout, fixture sharing, marker naming.
- Manifest-consistency check as new validator vs extension of `export_schemas`.
- Shim internals (bash fake-binary on PATH is the contract).

## Deferred Ideas

- DEP-03 / DEP-04 (live provisioning + FinOps) — v2, no live provisioning this milestone.
- Real production-grade SaaS write in live E2E-01 — deferred (needs disposable test tenant + cleanup).
- SI-04 / SI-05 ("Self-Evolving Surfaces" milestone) — already deferred at Phase 6.
