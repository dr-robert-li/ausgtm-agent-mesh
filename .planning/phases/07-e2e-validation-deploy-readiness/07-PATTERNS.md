# Phase 7: E2E Validation & Deploy-Readiness - Pattern Map

**Mapped:** 2026-06-08
**Files analyzed:** ~8 new/created files (1 new test package `tests/e2e/`, 1 new DEP harness package, fake-binary shims, 1 manifest-consistency validator/test)
**Analogs found:** 6 strong / 8 (NO analog: the PATH-shim subprocess harness, the manifest-consistency validator; **partial-gap: E2E-03's "job retry" leg has no deterministic analog — see E2E-03 §retry**)

> Phase 7 writes **no product code**. Every "file to create" is a test/harness that
> *assembles existing Phase 1–6 seams*. The source files below are **drive-surfaces**
> (read-only — the harness calls into them), never modified. The only files created are
> under `tests/e2e/`, a new DEP harness dir, and fake-binary shims.

---

## File Classification

| New/Created File (proposed) | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `tests/e2e/test_e2e_slack_write_gated.py` (E2E-01) | test | request-response (HTTP TestClient) | `tests/test_approval_security.py` | exact (TestClient + `_service` rebind) |
| `tests/e2e/test_e2e_mcp_durable_job.py` (E2E-02) | test | event-driven + durable-restart | `tests/test_checkpointer_resume.py` + `tests/smoke.py` (MCP path) | exact (durability) / role-match (MCP entry) |
| `tests/e2e/test_e2e_failure_modes.py` (E2E-03) | test | transform (fallback→retry→halt) | `tests/test_cascade.py` (fallback) + `tests/test_budget_halt_governed.py` (halt) | exact (fallback+halt) / **NO analog for the retry leg — see E2E-03 §retry** |
| `tests/e2e/conftest.py` (shared E2E fixtures, optional) | test-config | n/a | `tests/conftest.py` | role-match |
| `tests/e2e/test_e2e_*_live.py` variants (opt-in) | test | request-response / transform | `tests/test_hubspot_live.py`, `tests/test_cascade_live.py` | role-match |
| `tests/deploy/test_gcloud_idempotency.py` (DEP-01) | test | batch (subprocess + PATH shim) | **NONE** — loud-skip idiom from `conftest.pg_dsn` | partial (idiom only) |
| `tests/deploy/bin/gcloud`, `tests/deploy/bin/wrangler` (fake shims) | utility/fixture | batch | **NONE** | none |
| `tests/deploy/test_manifest_consistency.py` (DEP-02, D-11) | test | transform (YAML↔scripts↔schemas) | `agent_mesh.contracts.export_schemas` (machinery NOT a fit — see No Analog) | partial |

---

## Shared Patterns

These are the load-bearing cross-cutting idioms every Phase-7 file must copy exactly.

### SP-1 — TestClient + module-level `_service` rebind (THE D-03 keystone)

**Source:** `tests/test_approval_security.py` lines 60-65, 117-121.
**Apply to:** every default-lane E2E that drives ingress through the real FastAPI app (E2E-01 Slack/API; E2E-02's task-create + approval-callback legs).

`src/agent_mesh/api/app.py:31` builds `_service = TaskService()` **at import time** with its own
repository. A TestClient call therefore hits that module-level service, NOT the test's `repo`/`svc`.
The established fix is to **rebind the module global after constructing TestClient**:

```python
def _client():
    from fastapi.testclient import TestClient
    from agent_mesh.api import app as app_module
    return TestClient(app_module.app), app_module

# in the test, after building svc on the test repo:
client, app_module = _client()
app_module._service = svc  # bind the test repo/service into the app (REQUIRED)
```

Without the rebind, assertions read a different repo than the HTTP request mutated → green-on-a-lie.
This is the single most important pattern in the phase; smoke.py does NOT show it (smoke.py calls
`worker.process()` directly, never the HTTP surface).

### SP-2 — Three distinct live/durability gating axes (do NOT collapse to `live_creds`)

CONTEXT D-01 loosely says "double-gated by `live_creds`." The code shows **three different axes**.
Map each variant to its correct gate:

| Variant | Marker | Skip gate (the real axis) | Analog |
|---|---|---|---|
| E2E-01 live write (HubSpot sandbox / GWS draft) | `@pytest.mark.live` | **provider token** e.g. `HUBSPOT_PRIVATE_APP_TOKEN` (NOT `live_creds`) | `tests/test_hubspot_live.py:28,34-42` |
| E2E-02 durable restart-resume | **no `live` marker** | `langgraph.checkpoint.sqlite` importable (default lane) + `TEST_DATABASE_URL` for the Postgres lane | `tests/test_checkpointer_resume.py:45-49,86-96`; `conftest.pg_dsn:74-87` |
| E2E-03 live fallback + budget-halt | `@pytest.mark.live` | `live_creds` (model/gateway creds: `ANTHROPIC_API_KEY` / `VERTEX_PROJECT_ID` / `CF_AIG_WRAPPER_URL`) | `conftest.live_creds:124-135`; `tests/test_cascade_live.py` |
| DEP shellcheck / wrangler --dry-run | none | tool-on-PATH else **loud SKIP** (D-10) | idiom from `conftest.pg_dsn` skip shape |

E2E-02's default lane is the **sqlite fallback** and runs in `make test` (it is NOT `live`-marked);
its Postgres lane is `TEST_DATABASE_URL`-gated.

### SP-3 — `live` marker = whole-module opt-in

**Source:** `tests/test_hubspot_live.py:28`, `pyproject.toml:99-101`.
The only registered marker is `live`. Default suite = `pytest -m "not live"` (`Makefile:32`,
`pyproject.toml:93-98`). For live E2E variants, tag the whole module:

```python
pytestmark = pytest.mark.live  # whole module deselected without -m live
```

then SKIP inline on the specific credential axis (SP-2). No new marker is needed unless the planner
chooses one; the contract is "default lane stays green & creds-free."

### SP-4 — Schema/manifest path resolution (file-relative, cwd-independent)

**Source:** `tests/test_hubspot_live.py:30-31`; `export_schemas.py:17-18`.
Resolve manifest + schema dirs from `__file__`, never from cwd:

```python
_MANIFEST = Path(__file__).resolve().parents[1] / "manifests" / "tool_pack_manifest.yaml"
_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
# repo-root layout: manifests/{deployment.manifest.yaml, tool_pack_manifest.yaml}, schemas/*.schema.json
```

The DEP manifest-consistency check (D-11) consumes `manifests/deployment.manifest.yaml`,
`manifests/tool_pack_manifest.yaml`, and `schemas/*.schema.json`.

### SP-5 — Loud skip-if-absent (D-10 anti-silent-cap)

**Source:** `conftest.pg_dsn:82-87`, `agents_stack:91-103`, `test_checkpointer_resume._backend_available:30-37`.
Established shape: `pytest.skip("<tool> not installed; <what is being skipped>")` with a message that
*names the gap*. **Confirmed empirically: `shellcheck` and `wrangler` are both ABSENT on this dev
machine** — so the loud-skip is the **actual default-lane path**, not a corner case. The DEP harness
must assert it skips *loudly* (a recorded notice / a captured skip reason), never silently passes.

---

## Pattern Assignments

### `tests/e2e/test_e2e_slack_write_gated.py` — E2E-01 (test, request-response)

**Goal:** Slack request → evidence → write-gated SaaS action → approval → completion, **through the
real FastAPI app** (D-03), full chain asserted, creds-free default lane.

**Primary analog (mechanics):** `tests/test_approval_security.py` — TestClient + `_service` rebind
(SP-1), `_pause_on_write` helper, worker-issued-token readback.
**Sequence analog (chain shape):** `tests/smoke.py:27-39` — the write-gated assertion sequence to mirror.

**Chain to assert (mirror `smoke.py:27-39` but via HTTP):**
```python
# smoke.py:27-39 — the canonical write-gated sequence (in-memory; mirror through TestClient)
task = svc.create_task(request_from_slack(... text="create a hubspot deal for kickoff"))
assert worker.process(task.task_id) == "awaiting_approval"
(record,) = repo.list_approvals(task.task_id, "t")
svc.submit_approval_decision(approval_id, ApprovalDecision.APPROVED, "slack:U1", "slack")
assert worker.process(task.task_id) == "completed"
```

**Slack ingress entry (drive-surface `app.py:64-98`):** POST `/slack/events`. `verify_slack_signature`
(`slack_verify.py:26-29`) returns `True` when `SLACK_SIGNING_SECRET` is **unset** → the default lane
needs no signature. To exercise the real signature path (or a live variant), set the secret and the
`X-Slack-Request-Timestamp` / `X-Slack-Signature` headers per the v0 HMAC scheme (`slack_verify.py:39-42`).
Note: `/slack/events` returns a fast 200 ack and creates the task asynchronously — the E2E must then
drive the worker + approval-callback legs (the worker isn't auto-run by ingress).

**Token readback for the approval callback (copy `test_approval_security.py:42-57`):**
```python
stashed = repo.get_task(task.task_id).metadata["approval_tokens"]
token = stashed[record.approval_record_id]
# POST /v1/approvals with {approval_record_id, decision:"approved", approval_token: token}
```
The `/v1/approvals` endpoint (`app.py:101-130`) derives approver from the token (SEC-01); needs
`APPROVAL_SIGNING_SECRET` set (autouse fixture pattern `test_approval_security.py:27-32`).

**Worker write path (drive-surface `runner.py:122-161`):** proposed writes are gated, paused at
`AWAITING_APPROVAL`; resume at `runner.py:163-207` executes the approved write through the gateway.
Default lane: gateway returns `{"stub": True}` (`runner.py:214-220`) — assert completion, not a real write.

**Live variant `test_e2e_slack_write_gated_live.py` (D-07):** `pytestmark = pytest.mark.live`,
skip on the provider token (SP-2 row 1). The write is a **reversible draft/sandbox** (HubSpot sandbox
deal / GWS Drive draft) through the approval gate + sandbox, reusing the category-gated draft-force seam.

---

### `tests/e2e/test_e2e_mcp_durable_job.py` — E2E-02 (test, event-driven + durable-restart)

**Goal:** MCP request → long-running **checkpointed** mesh job → returns an artifact, proving **true
durability** via real restart-resume (D-04), not an in-memory saver.

**Primary analog (durability):** `tests/test_checkpointer_resume.py` — reuse its drop-then-reopen-
same-store restart simulation **verbatim** for the durable leg:

```python
# test_checkpointer_resume.py:56-83 — sqlite default lane (file-backed, NEVER :memory:)
db_path = str(tmp_path / "checkpoints.sqlite")
config = {"configurable": {"thread_id": _THREAD_ID}}          # DUR-02: thread_id == tenant-scoped task_id
conn = sqlite3.connect(db_path, check_same_thread=False)
saver = SqliteSaver(conn); graph = build_graph().compile(checkpointer=saver)
paused = graph.invoke({"prompt": _PROMPT}, config)
assert "__interrupt__" in paused                              # paused long run
del graph; del saver; conn.close()                           # simulated process death
conn2 = sqlite3.connect(db_path, check_same_thread=False); saver2 = SqliteSaver(conn2)
resumed = build_graph().compile(checkpointer=saver2).invoke(Command(resume=True), config)
assert "__interrupt__" not in resumed and resumed.get("decision") is True
```
Postgres lane: `test_checkpointer_resume.py:86-125` via `orchestrator._select_checkpointer()` +
`close_checkpointer()`, gated by `pg_dsn` / `_backend_available("langgraph.checkpoint.postgres")`.
Backend gate idiom: `_backend_available` (`:30-37`); `agents_stack` fixture (`conftest:90-103`).

**⚠ MCP ingress is NOT a TestClient route — design correction to D-03.**
`app.py` exposes only `/healthz`, `/v1/tasks`, `/slack/events`, `/v1/approvals`. **There is no `/mcp`
HTTP route.** `mcp_server.build_mcp_server` is FastMCP (`mcp_server.py:60`, `# pragma: no cover - needs
mcp extra`). So D-03's "ingress through the real TestClient" applies to **Slack/API only**, not MCP.

- **Default-lane MCP entry:** `request_from_mcp(...) → TaskService.create_task` (the `smoke.py:42-46`
  MCP path), NOT TestClient. Then drive the worker + the durable restart leg above.
- **Opt-in MCP-transport variant:** drive `build_mcp_server(service)` tools (`mcp_server.py:76-113`:
  `create_task`, `get_task`, `submit_approval`) — gated on the `mcp` runtime extra being importable.
- Either way the **approval** MCP parity uses `submit_approval_decision_with_token`
  (`mcp_server.py:22-57`) — the same token gate as HTTP.

**Artifact:** the run's reviewer summary / `OrchestrationResult` + any `result_summary` persisted on
the task (`runner.py:115-119`); assert a non-empty artifact survives the restart-resume.

---

### `tests/e2e/test_e2e_failure_modes.py` — E2E-03 (test, transform)

**Goal:** ONE combined run driving, in order, **model fallback → job retry → budget-limit halt → FAILED
terminal** (D-05), composing existing Phase-3 seams with **no new fault-injection harness**. This is a
**three-part** success criterion (ROADMAP SC-3: "model fallback, job retry, and budget-limit halt
together"). Two parts have exact analogs (fallback, halt); **the retry part does not — see §retry**.

**Fallback seam (analog `tests/test_cascade.py:51-80`):** build the real Router from yaml via
`build_router()`, force primary failure with the public litellm hooks (no creds, no network):
```python
resp = router.completion(
    model="low-complexity",
    messages=[{"role": "user", "content": "hi"}],
    mock_testing_fallbacks=True,   # primary raises InternalServerError -> cascade (RESEARCH Finding 4)
    mock_response="[fallback served]",  # fallback serves deterministically
)
assert resp.model == "gemini-1.5-pro"  # the FALLBACK deployment served, not the primary
```
Skip cleanly if the litellm runtime extra is absent (`test_cascade.py:42-48`).

**§retry — job-retry leg has NO deterministic analog (planner must resolve).**
Verified: `tests/test_pubsub_dispatch.py` (read in full) does **NOT** exercise retry/redelivery — it
covers (1) an emulator-gated publish→consume roundtrip (`:41-87`, skipped unless `PUBSUB_EMULATOR_HOST`)
and (2) the in-process fallback drain (`:90-118`). Neither retries a failed delivery. The **only**
"job retry" wiring in the repo is **deploy-time config, not a tested seam**: `gcp_bootstrap.sh:70-98`
sets `--dead-letter-topic` + `--max-delivery-attempts=5` on the worker subscription (Pub/Sub
redelivery). That is real-GCP-only and out of this milestone's deploy-ready ceiling (no live
provisioning). Two distinct "retry" notions exist, and the planner must pick one:
- **(a) Pub/Sub job redelivery** — the literal "job retry." No deterministic analog; would need a new
  fault-injection harness, which **D-05 explicitly forbids** ("no new fault-injection harness"). Best
  done as an emulator-gated opt-in test (skip shape like `test_pubsub_dispatch.py:35-38`), OR asserted
  only as deploy-config consistency in DEP-01 (the `--max-delivery-attempts` flag is present in
  `gcp_bootstrap.sh`).
- **(b) In-cascade model retry** — litellm's `num_retries`/cascade recovery, which is part of the
  **fallback** seam already mapped above (the cascade IS the mid-run retry-then-recover). Under this
  reading the three-part criterion collapses to fallback(+retry)→halt, and the retry assertion is the
  fallback test asserting recovery before the halt.

**Recommendation for the planner (not a decision — flagged for the plan-checker):** treat (b) as the
deterministic default-lane proof of mid-run retry-recovery (no new harness, satisfies D-05), and cite
(a) the Pub/Sub `--max-delivery-attempts=5` config in the **DEP-01** manifest/script consistency check
as the durable-redelivery evidence. If a literal Pub/Sub redelivery test is required, it must be a NEW
emulator-gated harness and the "no new fault-injection harness" constraint in D-05 needs an explicit
exception. **Do not leave retry silently unmapped — it is a named success-criterion element.**

**Budget-halt seam (analog `tests/test_budget_halt_governed.py`):** force over-budget by recording an
over-cap ledger row for the budget owner (`== settings.tenant_id`), then drive the real worker path:
```python
# governed_env fixture (:44-71): InMemoryRepository pinned as the process singleton + TENANT_ID/CLIENT_SLUG
repo.record_budget_event(BudgetEvent(... budget_owner=_TENANT, estimated_cost_usd=100.0))  # past $50 cap (:73-90)
monkeypatch.setattr(graph_module, "_model_credentials_present", lambda: True)  # force real _delegate (:162)
state = Worker(repo=repo).process(task.task_id)
assert state == TaskState.FAILED.value                       # governed FAILED terminal (:175-177)
halt = [e for e in repo.list_gateway_events(task.task_id, _TENANT) if e.model_route == "budget_halt"]
assert len(halt) == 1 and halt[0].provider_status is None    # exactly one budget_halt event, no provider leak
```
Assert each transition + the `budget_halt` `gateway_event` + the FAILED terminal (D-05). The
"halt-before-provider" leak guard is `test_budget_halt_governed.py:164-187` (`_boom` get_chat_model).

**Ordering note (forced by seam semantics):** fallback + retry are mid-run recovery and must *succeed*
first; the budget then exhausts and the run halts to FAILED. The seams currently live in separate
tests; E2E-03 composes them into one run (planner decides whether one process or staged asserts).

**Live variant (D-06/D-08):** `pytestmark = pytest.mark.live` + `live_creds` (SP-2 row 3). Set a
**few-cents budget** routed to the **cheapest tier** so the real halt fires for pennies.

---

### Deploy-readiness: `tests/deploy/test_gcloud_idempotency.py` + fake shims — DEP-01 (test, batch)

**Goal:** prove the `gcloud`/`wrangler` resource-detection (reuse-vs-create) **logic** locally via a
PATH-shimmed fake binary (D-09). **No existing analog** (see No Analog Found) — build new.

**Drive-surfaces (read-only; the scripts under test):**
- `scripts/gcp_bootstrap.sh` — the describe-before-create guards to exercise:
  - project: `:25-40` (`gcloud projects describe` → create only if `CREATE_PROJECT=true`)
  - Artifact Registry: `:58-62` (`repositories describe ... || create`)
  - Pub/Sub topics/subs **+ DLQ/redelivery wiring**: `:64-98` (`--dead-letter-topic`,
    `--max-delivery-attempts=5` — the deploy-config evidence for E2E-03's job-retry leg, §retry option a)
  - service accounts: `:100-104`
  - Cloud SQL instance + db: `:130-145`
  - required env contract: `:14-22` (`: "${PROJECT_ID:?...}"`, REGION/CREATE_PROJECT/SQL_* defaults)
- `scripts/gcp_deploy_core.sh` — Cloud Run jobs create-vs-update branch: `deploy_job` `:72-90`
  (`gcloud run jobs describe ... && action="update"` else `create`); env contract `:9-19`.
- `scripts/cf_deploy_ai_gateway_worker.sh` — `:12-15` env contract; `:22-30` reuse-gateway branch +
  `wrangler deploy`.

**Shim contract (D-09):** a fake `gcloud` (and `wrangler`) on `PATH` that:
1. records each `describe`/`whoami`/`deploy` invocation,
2. returns exit 0 ("exists") or non-0 ("absent") per a test-controlled fixture state,
so the test asserts: when a resource "exists", the `... describe >/dev/null 2>&1 || create` short-
circuits and `create` is NEVER invoked; when absent, `create` IS invoked. Drive the script with
`subprocess.run([...], env={"PATH": shim_dir + os.pathsep + ..., "PROJECT_ID": ...})`.

**Lint/dry-run legs (D-10, loud skip — SP-5):** `shellcheck scripts/*.sh` and
`wrangler --dry-run` run only when the tool is on PATH (both **confirmed absent here** → these SKIP
loudly by default). Use the `pytest.skip("shellcheck not installed; gcloud-script lint skipped")` shape.

---

### Deploy-readiness: `tests/deploy/test_manifest_consistency.py` — DEP-02 / D-11 (test, transform)

**Goal:** assert `deployment.manifest.yaml` ↔ tool-pack manifest ↔ scripts ↔ schemas are consistent.
**Claude's-Discretion (D-11):** new validator vs extend `export_schemas`. **Evidence points to a NEW
validator** — see No Analog Found for why `export_schemas` does not fit.

**Three concrete cross-checks (drive-surfaces, read-only):**
1. **Env-var contract: manifest fields ↔ script `${VAR:?}` requirements.**
   Scripts require (`gcp_bootstrap.sh:14`, `gcp_deploy_core.sh:9-19`, `cf_deploy_ai_gateway_worker.sh:12-15`):
   `PROJECT_ID`, `REGION`, `TENANT_ID`, `CLIENT_SLUG`, `MODEL_ROUTE_PROFILE`, `AR_REPO`, `SQL_INSTANCE`,
   `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_AI_GATEWAY_ID`, `WRANGLER_ENV`, `REUSE_EXISTING_CLOUDFLARE_GATEWAY`,
   `CREATE_PROJECT`/`BILLING_ACCOUNT_ID`. Manifest supplies these as (`deployment.manifest.yaml`):
   `deployment.project_id/region/tenant_id/client_slug` (`:8-12`), `model_routes.default_profile` (`:65`),
   `gcp.artifact_registry_repo` (`:20`), `gcp.cloud_sql.instance_name` (`:22`),
   `cloudflare.account_id/ai_gateway_id/wrangler_env/reuse_existing_gateway` (`:41-44`),
   `deployment.create_project_if_missing/billing_account_id` (`:11-12`). Assert no orphan on either side.
2. **Tool-pack pointer + schema coverage.** `deployment.manifest.yaml:114-115`
   `tool_packs.manifest_path: "manifests/tool_pack_manifest.yaml"` must resolve; each tool in
   `tool_pack_manifest.yaml` `tools:` should have matching `schemas/<tool>.input/output.schema.json`
   (SP-4 path resolution). `integration_styles` (`:118`) must be a known set.
3. **Required-stack assertions (acceptance-criteria guard).** `deployment.manifest.yaml:57-62` declares
   `agent_framework: langchain+langgraph+deepagents`, `observability: langfuse`, `langsmith:
   optional-alternative-only` — assert these hold (CLAUDE.md §6 AC-1/AC-2; LangSmith never required).

---

## No Analog Found

| Proposed File / Element | Role | Data Flow | Reason no analog |
|---|---|---|---|
| `tests/deploy/test_gcloud_idempotency.py` + `tests/deploy/bin/{gcloud,wrangler}` shims | test + fixture | batch | **No subprocess-driving or fake-binary-on-PATH test exists in the suite.** The `.sh` scripts have never been exercised by a test. The only reusable idiom is the loud skip-if-absent (SP-5). The shim + `subprocess.run(env=...)` harness is genuinely new. |
| `tests/deploy/test_manifest_consistency.py` (D-11) | test | transform | `agent_mesh.contracts.export_schemas` is the only "schema machinery," and it does **Pydantic `CONTRACT_MODELS → schemas/contracts/*.schema.json`** (`export_schemas.py:13,21-31`). It **never reads the YAML manifests**, never validates env-var↔script contracts, and has no consistency-checking concept. Extending it would conflate Pydantic-export with YAML-consistency — distinct concerns. Evidence favors a **new validator** (the planner owns the final call per D-11). |
| E2E-03 **job-retry leg** (sub-element, not a whole file) | test (seam) | transform | **No deterministic retry/redelivery test exists.** `test_pubsub_dispatch.py` covers publish/consume + in-process drain but never redelivery. The only retry wiring is deploy-config (`gcp_bootstrap.sh:70-98` `--max-delivery-attempts=5`), which is real-GCP-only. D-05 forbids a new fault-injection harness, so the planner must either (b) read "retry" as litellm in-cascade recovery folded into the fallback seam, or (a) assert the redelivery config in DEP-01. See E2E-03 §retry for the full breakdown. **Must be explicitly resolved in the plan, not left implied.** |

---

## Drive-Surfaces (read-only; harness calls in, never modifies)

| File | Lines of interest | What the E2E/DEP harness uses |
|---|---|---|
| `src/agent_mesh/api/app.py` | `31` (`_service` global), `39-53` (`/v1/tasks`), `64-98` (`/slack/events` + fast-ack), `101-130` (`/v1/approvals` token gate) | TestClient ingress (SP-1) |
| `src/agent_mesh/api/slack_verify.py` | `26-29` (no-secret → True), `39-42` (v0 HMAC) | Slack default-lane bypass + live-signature path |
| `src/agent_mesh/api/mcp_server.py` | `22-57` (`submit_approval_decision_with_token`), `60-113` (`build_mcp_server` FastMCP, mcp-extra only) | E2E-02 MCP approval parity + opt-in transport variant |
| `src/agent_mesh/services/task_service.py` | `request_from_slack`, `request_from_mcp`, `create_task`, `submit_approval_decision` | task creation + approval |
| `src/agent_mesh/services/dispatch.py` | `InProcessDispatcher`, `PubSubDispatcher` | E2E-02 default vs Pub/Sub dispatch; E2E-03 §retry option (a) |
| `src/agent_mesh/worker/runner.py` | `50-161` (run + write-gate), `163-207` (resume), `214-229` (`_execute` stub) | worker drive |
| `src/agent_mesh/worker/graph.py` | `build_graph()` (`__interrupt__` at write_gate), `_delegate`, `_model_credentials_present` | E2E-02 checkpointed graph; E2E-03 halt |
| `src/agent_mesh/worker/orchestrator.py` | `_select_checkpointer()`, `close_checkpointer()`, `run_mesh`, `resume_mesh`, `langgraph_available()`/`deep_agents_available()` | durable checkpointer lifecycle |
| `config/model_gateway.config.yaml` | cascade map (low→medium→high) | E2E-03 fallback (via `build_router()`) |
| `scripts/gcp_bootstrap.sh` | `14-22`, `25-40`, `58-62`, `64-98` (incl. DLQ/`--max-delivery-attempts`), `100-104`, `130-145` | DEP-01 idempotency-logic targets; E2E-03 §retry (a) evidence |
| `scripts/gcp_deploy_core.sh` | `9-19`, `72-90` (`deploy_job` create/update) | DEP-01 |
| `scripts/cf_deploy_ai_gateway_worker.sh` | `12-15`, `22-30` | DEP-02 |
| `manifests/deployment.manifest.yaml` | `5-12`, `19-22`, `40-44`, `57-62`, `64-67`, `114-118` | D-11 cross-checks |
| `manifests/tool_pack_manifest.yaml` | `tool_pack:` header, `tools:` (372 lines) | D-11 schema coverage |
| `schemas/*.schema.json` | per-tool input/output | D-11 coverage |

---

## Metadata

**Analog search scope:** `tests/`, `src/agent_mesh/api/`, `src/agent_mesh/worker/`,
`src/agent_mesh/contracts/`, `scripts/`, `cloudflare/`, `manifests/`, `schemas/`.
**Files scanned:** ~19 read in full or in targeted ranges.
**Empirically confirmed:** `shellcheck` and `wrangler` are absent on this dev machine (D-10 loud-skip
is the default-lane path); `app.py` has no `/mcp` route (E2E-02 MCP design correction);
`test_pubsub_dispatch.py` does NOT exercise retry/redelivery (E2E-03 §retry has no deterministic analog).
**Pattern extraction date:** 2026-06-08
