# Phase 7: E2E Validation & Deploy-Readiness - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Assemble all prior layers and prove the platform end-to-end, then validate the deploy
scripts are idempotent and GCP-ready **without provisioning any live cloud resources**.

Three E2E proofs + failure modes + deploy-readiness checks:
- **E2E-01** — Slack request → evidence → write-gated SaaS action → approval → completion.
- **E2E-02** — MCP request → long-running checkpointed mesh job → returns an artifact.
- **E2E-03** — failure E2E exercising model fallback + job retry + budget-limit halt **together**.
- **DEP-01** — `gcloud` bootstrap + deploy scripts: lint + dry-run/syntax + mocked-`gcloud`
  resource-detection (idempotency *logic* proven locally; true live idempotency = DEP-03, deferred).
- **DEP-02** — Cloudflare `wrangler` deploy script lint + dry-run; deployment + tool-pack
  manifests schema-consistent. Local-validation ceiling, no live publish.

The WHAT is fixed by ROADMAP.md §"Phase 7" + REQUIREMENTS.md (E2E-01/02/03, DEP-01/02).
This phase clarifies only HOW to implement those proofs/checks. **No new capabilities**;
**no live GCP provisioning** this milestone (DEP-03/04 are v2).

</domain>

<decisions>
## Implementation Decisions

### E2E realism & lane (cross-cutting)
- **D-01 (dual-lane E2E):** Every E2E proof runs **deterministic + creds-free in the default
  lane** (full chain assertions, CI-green, no providers) **AND** has a **thin opt-in `live`
  variant** that plugs the real seams. Matches the established Phase 1–6 pattern (default
  creds-free; real exercised only in `make test-live`, operator-deferred). Live variants are
  independently skippable and double-gated by the `live_creds` fixture / `live` marker.
- **D-02:** "Real" gets exercised in the live variants only; the default lane simulates
  providers in-process. Existing per-adapter live lanes (P4/P5) remain the per-tool real proof;
  the live E2E variant proves the **assembled chain** end-to-end with real seams.

### Harness substrate & durability
- **D-03 (dedicated suite):** Build a **dedicated `tests/e2e/` suite** (not an extension of
  `tests/smoke.py`). Ingress driven through the real **FastAPI `TestClient`** (real app wiring),
  not direct service calls, so the ingress→task→dispatch→worker→approval→resume chain is proven
  through the real API surface. `tests/smoke.py` stays as the lightweight no-DB smoke check.
- **D-04 (real durability for E2E-02):** E2E-02 rides the **real Postgres checkpointer
  restart-resume** mechanism — `TEST_DATABASE_URL`-gated, reusing the
  `test_checkpointer_resume.py` drop-then-reopen-same-store proof — so the long checkpointed
  job demonstrates **true durability** (not an in-memory saver). **sqlite-backed fallback**
  when no Postgres is available, so the default lane stays portable/green. (Rationale: avoid
  hiding the durability SPOF behind an in-memory store.)

### Failure-mode E2E (E2E-03)
- **D-05 (one combined run + live variant):** E2E-03 is a **single combined run** that drives,
  in order, **model fallback (GW-03 lane) → job retry → budget-limit halt**. Ordering is forced
  by the seams' semantics: fallback + retry are mid-run recovery and must *succeed* first; then
  the budget exhausts and the run **halts to FAILED terminal**. Assert each transition + the
  `budget_halt` `gateway_event` + the FAILED terminal state. Reuse the existing Phase-3 seams
  (GW-03 fallback lane, budget cents-cap, retry) deterministically — **no new fault-injection
  harness**.
- **D-06 (live variant):** Add an opt-in `live` variant of E2E-03 exercising a **real model
  fallback + real budget-halt**, bounded by **D-08**.

### Live-lane safety posture (forced by D-01/D-06)
- **D-07 (E2E-01 live write = real draft/sandbox only):** The live E2E-01 write performs a
  **real but reversible draft/sandbox write** (e.g. HubSpot sandbox deal / Google Workspace
  Drive draft) through the **approval gate + sandbox**, reusing the category-gated draft-force
  seam. Proves the real tool-write chain without mutating production data. (No real
  production-grade committed write this milestone.)
- **D-08 (E2E-03 live spend = tiny cents-cap):** The live E2E-03 variant sets a **few-cents
  budget** and routes to the **cheapest model tier**, so the **real budget-halt** fires for
  ~pennies. Proves the real halt cheaply rather than burning toward the full $50 budget.

### Deploy mock strategy (DEP-01/02)
- **D-09 (PATH-shim fake binaries):** Prove gcloud/wrangler idempotency *logic* via a
  **fake `gcloud`/`wrangler` shim on `PATH`** that records `describe`→`create` branch decisions;
  a **pytest** harness drives the scripts and asserts the reuse-vs-create logic (resource
  detection short-circuits creation when a resource "exists"). Faithful to how the scripts
  actually run.
- **D-10 (skip-if-absent, loud):** `shellcheck` (lint) and `wrangler --dry-run` run **when the
  tool is installed**, else the check **SKIPs with a loud, logged notice** — never a silent gap
  (per the "no silent caps" anti-pattern). Keeps the default suite green/portable on any dev
  machine while still running the real linters in CI where they're installed.
- **D-11 (manifest schema-consistency):** A check asserts the **deployment manifest + tool-pack
  manifest** are schema-consistent (env-var contract vs scripts; manifest fields vs declared
  schemas). Planner decides whether to extend the existing schema-export machinery or add a
  dedicated validator.

### Claude's Discretion
- Exact `tests/e2e/` module layout, fixture sharing with existing conftest, and marker naming.
- Whether DEP manifest-consistency is a new validator vs an extension of
  `agent_mesh.contracts.export_schemas`.
- The specific shim implementation language (bash fake-binary on PATH is the contract;
  internals are open).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` §"Phase 7: E2E Validation & Deploy-Readiness" — goal + 4 success criteria.
- `.planning/REQUIREMENTS.md` §Validation (E2E-01/02/03), §Deploy-Readiness (DEP-01/02), and the
  DEP-03/04 v2 deferral boundary.
- `docs/production-readiness-caveats.md` — defines the deploy-ready-only ceiling and what's
  explicitly out of scope (live provisioning, HA, etc.).

### E2E harness — existing patterns to reuse/extend
- `tests/smoke.py` — existing in-memory full-chain harness (ingress→approval→resume); reference
  for the chain shape, NOT the substrate for the new suite (D-03).
- `tests/test_checkpointer_resume.py` — the sqlite-gated + Postgres-gated (`TEST_DATABASE_URL`)
  drop-then-reopen restart-resume proof E2E-02 reuses (D-04).
- `tests/conftest.py` — `live_creds` fixture + `live` marker gating (creds-free default lane).
- `pyproject.toml` §pytest markers — `live` marker definition; default suite = `-m "not live"`.
- `tests/test_budget_halt_governed.py`, `tests/test_approval_gating.py`,
  `tests/test_approval_security.py`, `tests/test_orchestration_graph.py` — seams E2E-03/E2E-01
  compose (budget halt, approval gate, fallback/retry, graph).
- `src/agent_mesh/api/app.py` (FastAPI app), `src/agent_mesh/api/slack_verify.py`,
  `src/agent_mesh/api/mcp_server.py` — ingress surfaces driven via `TestClient`.
- `src/agent_mesh/worker/runner.py`, `src/agent_mesh/worker/graph.py` — worker + graph the E2E
  runs drive.

### Deploy scripts under validation
- `scripts/gcp_bootstrap.sh` (152 lines, idempotent-by-design; `gcloud ... describe` guards),
  `scripts/gcp_deploy_core.sh` (103 lines) — DEP-01 targets.
- `scripts/cf_deploy_ai_gateway_worker.sh` (37 lines) + `cloudflare/ai-gateway-wrapper/wrangler.toml`
  — DEP-02 targets.
- `RUNBOOK.md` — local smoke checks + deployment runbook (env-var contract the manifest-consistency
  check validates against).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/smoke.py`: proven full-chain assertion sequence (write-gated + read-only) to mirror in
  `tests/e2e/` but through `TestClient` + real repo.
- `test_checkpointer_resume.py` restart mechanism: directly reusable for E2E-02's durable
  checkpointed-job proof (sqlite + Postgres lanes already exist).
- `live_creds` fixture + `live` marker: the established double-gate for every opt-in live variant.
- Phase-3 seams: GW-03 fallback lane, budget cents-cap → `budget_halt` gateway_event + FAILED
  terminal, retry — compose directly into E2E-03 with no new fault harness.
- Category-gated draft-force seam (financial/write writes): backs D-07's real draft/sandbox write.

### Established Patterns
- Default suite creds-free/deterministic (`make test` = `pytest -m "not live"`); real
  providers/models only in `make test-live`. Every new live E2E variant follows this.
- Durable proofs use drop-then-reopen-same-store to simulate process death (never `:memory:`,
  never a real timer).
- gcloud scripts already idempotent-by-design (describe-before-create); DEP work proves the
  *logic*, doesn't add idempotency.

### Integration Points
- New `tests/e2e/` suite ↔ `agent_mesh.api.app` (TestClient) ↔ real repository/checkpointer
  (sqlite default / Postgres when `TEST_DATABASE_URL` set).
- DEP harness ↔ `scripts/*.sh` via PATH-shimmed fake `gcloud`/`wrangler`.
- Manifest-consistency check ↔ deployment manifest + tool-pack manifest + `export_schemas`.

</code_context>

<specifics>
## Specific Ideas

- User consistently chose the **real-validation** branch in every area (deterministic default
  **plus** opt-in live), reasoning from controllability / avoiding hidden SPOFs (in-memory
  durability, silent tool-skip gaps) — see [[discuss-phase-decision-style]].
- Live writes stay **reversible** (draft/sandbox); live spend stays **bounded** (cents-cap).
  Real chain proven, blast radius and cost contained.

</specifics>

<deferred>
## Deferred Ideas

- **DEP-03 / DEP-04** (live Cloud SQL + Cloud Run provisioning in `australia-southeast1`, live
  E2E run, FinOps review vs $65 infra / $50 model guardrails) — explicitly **v2**, out of this
  milestone (no live provisioning).
- **Real production-grade SaaS write** in live E2E-01 (vs draft/sandbox) — deferred; would need a
  disposable test tenant + cleanup. Revisit if/when a live test tenant exists.
- **SI-04 / SI-05** ("Self-Evolving Surfaces" milestone) — unrelated to Phase 7; already deferred
  at Phase 6.

</deferred>

---

*Phase: 7-E2E Validation & Deploy-Readiness*
*Context gathered: 2026-06-08*
