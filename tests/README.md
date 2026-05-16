# Testing strategy

Unit tests are necessary but **insufficient** for an agentic system. A green
unit suite can coexist with a broken swarm, a credential leak, or a task
tree that no one can reconstruct after the fact. The layout below makes
each failure mode someone's responsibility.

All layers run under `pytest` with the markers declared in
`pyproject.toml`. Default `pytest` runs everything except `slow`.

```
tests/
├── unit/           pure unit tests (no DB, no network, no Temporal)
├── contract/       Pydantic + JSON-schema round-trips; version drift
├── workflow/       Temporal workflow tests via the SDK test harness
├── integration/    real Slack/Monday/Sheets/tl;dv sandbox calls
├── dynamic/        Swarm Supervisor: waves, recursion, ledger
├── system/         end-to-end Slack → API → Temporal → tools → Slack
├── chaos/          failure injection: worker death, tool 5xx, timeouts
├── observability/  reconstruct a task tree from the five log streams
└── fixtures/       shared test data
```

## 1. Unit (`tests/unit/`, marker `unit`)

Plain Python. Fast. Pure functions, helpers, parsers, small classes.
No DB, no network, no Temporal harness. If a unit test needs any of
those, it belongs in a layer below.

## 2. Contract (`tests/contract/`, marker `contract`)

The Task and SpawnLedger contracts are the bus of the system. Each
contract test asserts:

- Round-trip: `Model(**Model(...).model_dump()) == original`.
- Forbidden extras: unknown fields raise `ValidationError`.
- Required fields: missing fields raise.
- JSON schema is stable: a snapshot of `Model.model_json_schema()` is
  diffed; intentional changes update the snapshot in the same PR that
  bumps the contract version.

Touching `packages/contracts/` without a matching `tests/contract/` diff
is a review-blocker.

## 3. Workflow (`tests/workflow/`, marker `workflow`)

Uses Temporal's `WorkflowEnvironment` test harness (time-skipping or
local server). For each workflow:

- Activities are mocked at the seam (`activity.mock`).
- Determinism: replay the history; any non-determinism is a failure.
- Signals and queries: HITL approve/reject, kill-switch trip, status query.
- Failure paths: activity `ApplicationError`s surface as expected Task
  states (`FAILED` with `state_reason` set).

## 4. Integration (`tests/integration/`, marker `integration`)

Real external services against **sandbox tenants only**. Gated by
environment variables — skip if creds absent so CI without sandbox
access stays green.

- Slack: a dedicated test workspace; post + react + thread.
- Monday: a test board; read/write rows.
- Google Sheets: a test spreadsheet; read + write ranges.
- tl;dv: a test meeting transcript fixture.

Credentials come from environment, not from fixtures. The Tool Gateway
is the only path; tests assert it never logs raw secrets.

## 5. Dynamic swarm (`tests/dynamic/`, marker `dynamic`)

The Swarm Supervisor's behaviour under varying plans. Generate plans
(parametric `pytest` fixtures) and assert, for each:

- Number of waves ≤ `policy.limits.max_waves`.
- Children per wave ≤ `policy.limits.max_child_agents_per_wave`.
- A `SpawnLedger` row exists **before** every child Task in DB ordering.
- Recursion: at `depth+1 > max_recursion_depth`, the supervisor writes a
  Decision-log row `spawn_denied: max_recursion_depth` and the child is
  not created.
- Runaway: crossing `max_total_spawns` cancels the parent with
  `state_reason: runaway_swarm` and disposes in-flight children
  `cancelled`.
- HITL triggers: each of the eight triggers from the reference arch
  transitions the Task to `AWAITING_HITL` with the right
  `recommended_action`.
- Kill switch: tripping platform/tenant/routine/entrypoint/depth refuses
  new spawns at each scope.
- DLQ: a poison-pill child lands in DLQ exactly once; replay creates a
  *new* child Task; the DLQ row is never mutated.

## 6. System (`tests/system/`, marker `system`)

End-to-end against the POC scenarios in `README.md`. The entire stack
(API + workers + Slack + MCP + Postgres + Temporal) is brought up via
Docker Compose. Assertions are at the Slack surface and at the Task
state in Postgres.

## 7. Chaos (`tests/chaos/`, marker `chaos`)

Failure injection. For each fault, assert the system recovers without
violating invariants:

- Kill a worker mid-activity → Temporal retries; Task does not
  duplicate side effects (idempotency keys).
- Tool returns 5xx → Tool Gateway surfaces a typed error; activity
  retries within policy; Task does not silently succeed.
- Activity heartbeat expires → workflow records a Decision-log row
  and either retries or fails with `state_reason: heartbeat_timeout`.
- Budget exhaustion mid-run → Task moves to `AWAITING_HITL`.
- Postgres restart → API returns 503 readiness; in-flight workflows
  resume cleanly after recovery.

## 8. Observability replay (`tests/observability/`, marker `observability`)

Given **only** the five log streams (Event, Decision, Action,
Validation, Evaluation) for a completed Task, reconstruct:

- The Task tree (parent/root relationships).
- Final `state` and `state_reason`.
- Every spawn decision and its disposition.
- Every tool call (handle + trust tier, never raw credentials).
- Every validator and evaluator verdict.

Any gap fails the suite. This is the canary on observability quality —
if logs don't carry the story, the system isn't operable.

## Running

```bash
pytest                          # all except `slow`
pytest -m unit                  # fastest layer
pytest -m "contract or workflow"
pytest -m integration           # requires sandbox creds
pytest -m "dynamic or system"   # requires Docker Compose up
pytest -m chaos                 # requires Docker Compose up
pytest -m observability
```
