# ausgtm-agent-mesh

Local-first Python POC runtime for the **Agentic Mesh** described in
[`dr-robert-li/agentic-mesh-reference-arch`](https://github.com/dr-robert-li/agentic-mesh-reference-arch)
(currently tracking `v0.1.3`).

This repository is the **implementation** of the architecture. The reference
repo defines contracts, planes, and invariants; this repo wires them into a
runnable system using Python, FastAPI, Temporal, Postgres+pgvector, Slack Bolt,
the MCP Python SDK, and the Anthropic Claude Agent SDK.

> **Scope.** Local-first POC. No Temporal Cloud. First non-local deployment
> target is AWS ECS Fargate.

---

## Purpose

Demonstrate that the reference architecture's four-plane design (entry /
control / execution / persistence) can be implemented as a real, observable,
testable system with:

- **Durable orchestration** via local Temporal (Python SDK).
- **Agent execution** inside Temporal activities, never inside workflows.
- **Tool execution** via a single Tool Gateway that owns all credentials.
- **Direct Anthropic Claude Agent SDK** as the primary model path, with
  AWS Bedrock and GCP Vertex AI adapters as fallbacks.
- **Slack** as the primary end-user surface.
- **MCP** as the entrypoint for external agents and self-loopback.
- **Postgres + pgvector** as the system of record **for mesh state** (Tasks,
  SpawnLedger, log streams, routines/releases) and the vector store from day one.
- **Context and Evidence Knowledge Layer** — a tenant-scoped cache + index +
  evidence-pointer layer in front of external tools. **Not** a system of
  record; ground truth stays in the external tools.
- **Intake contract** with a cheap S-tier feasibility check at the entry plane.
- **Egress-only verification** with eight deterministic guards (schema,
  claim-evidence map, evidence resolvable, freshness, source authority,
  tenancy, tier/policy, budget) — no LLM in the verification loop.
- **Swarm Supervisor** with wave-based dynamic spawning, conservative recursion,
  policy / budget / risk / marginal-utility gates, an append-only spawn ledger,
  HITL escalation, kill switch, and DLQ.

The POC's job is to make the boundaries in [`CLAUDE.md`](./CLAUDE.md) real and
verifiable — not to ship every routine.

---

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| API | FastAPI + uvicorn |
| Orchestration | Temporal (local server, `temporalio` Python SDK) |
| Agents (primary) | Anthropic Claude Agent SDK |
| Agents (fallbacks) | AWS Bedrock adapter, GCP Vertex AI adapter |
| Slack | `slack_bolt` (Socket Mode for local) |
| MCP | `mcp` Python SDK (server + client) |
| Persistence | Postgres 16 + `pgvector` |
| DB driver | `asyncpg` / `psycopg` + SQLAlchemy 2.x |
| Contracts | Pydantic v2 |
| Observability | OpenTelemetry (traces/metrics/logs) |
| Tests | `pytest`, `pytest-asyncio`, Temporal test harness |

External integrations targeted for v1: **Slack**, **Monday.com**,
**Google Sheets**, **tl;dv / external meeting artifacts**.

---

## Repo structure

```
apps/
  api/          FastAPI — system of record. Only write surface.
  slack/        Slack Bolt app. Calls the API. Does not write Task state.
  mcp/          MCP server. External-agent entrypoint and loopback.
  workers/      Temporal worker process(es) that host workflows + activities.
packages/
  contracts/    Pydantic models: Task, Policy, Routine, SpawnLedger,
                HITLDecision, EvaluationRecord, Intake, KnowledgeLayerEntry,
                ClaimEvidenceMap, EgressCheckRecord, etc.
  workflows/    Temporal workflow definitions (deterministic; orchestration only).
  activities/   Temporal activities. Agent SDK calls live here.
  model_gateway/  Anthropic (primary) + Bedrock + Vertex adapters.
  tool_gateway/   The only place credentials live. Tool trust tiers enforced here.
  policy/       Policy engine, evaluator, validator services.
  registry/     Routine + Release manifest registry.
  observability/ OTel setup, the five log streams, log helpers.
infra/
  local/        docker-compose (Postgres+pgvector, Temporal), seed scripts.
  aws/          ECS Fargate stubs (later).
tests/
  unit/         Pure unit tests.
  contract/     Pydantic + JSON-schema round-trips, contract version drift.
  workflow/     Temporal workflow tests via the SDK test harness.
  integration/  Real Slack/Monday/Sheets/tl;dv against sandboxes.
  dynamic/      Swarm Supervisor: wave/recursion/spawn-ledger behaviour.
  system/       End-to-end Slack → API → Temporal → tools → Slack.
  chaos/        Failure injection: worker death, activity timeout, tool 5xx.
  observability/ Reconstruct a task from logs alone (five-stream replay).
  fixtures/     Shared test data.
```

See [`tests/README.md`](./tests/README.md) for the full testing strategy.

---

## Local quickstart

> Nothing is auto-installed yet — this is a scaffold. The commands below are
> the intended workflow.

### Prerequisites

- Python 3.11+
- Docker + Docker Compose
- An Anthropic API key (primary path)
- Optional: AWS creds (Bedrock), GCP creds (Vertex), Slack app, Monday API
  token, Google Sheets service account, tl;dv API key

### Bring up infra

```bash
cp .env.example .env
# edit .env with real values
docker compose -f infra/local/docker-compose.yml up -d
```

This starts:

- **Postgres 16 + pgvector** on `localhost:5432`
- **Temporal** (server + UI) on `localhost:7233` / UI `localhost:8233`

### Install Python deps

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

### Run the processes

```bash
# 1. API (system of record)
uvicorn apps.api.main:app --reload --port 8000

# 2. Temporal worker (hosts workflows + activities)
python -m apps.workers.main

# 3. Slack app (Socket Mode)
python -m apps.slack.main

# 4. MCP server
python -m apps.mcp.main
```

---

## POC scenarios

The POC ships with a small set of end-to-end scenarios that exercise the full
control / execution / persistence loop. Each must be reconstructable from the
five log streams alone (see `tests/observability/`).

1. **Slack → simple task.** A user `@mentions` the bot with a goal. API
   creates a `Task`, Temporal workflow runs a single-agent activity, result
   posted back to Slack. Exercises: entrypoint=slack, no spawning, no HITL.

2. **Slack → wave-based swarm.** Goal that requires decomposition. Planner
   produces a plan with ≥2 waves; Swarm Supervisor spawns child tasks within
   `max_child_agents_per_wave`; spawn ledger rows precede every child;
   results merged. Exercises: wave gating, ledger, marginal utility.

3. **Monday.com + Sheets cross-tool task.** A goal that requires reading a
   Monday board and writing a Google Sheet. Exercises: Tool Gateway,
   trust tiers (`read_sensitive` → `write_revocable`), credential isolation.

4. **tl;dv meeting → action extraction.** Ingest a meeting artifact via tl;dv,
   produce action items, optionally fan out into a swarm. Exercises:
   external-agent style entry via MCP and/or scheduled API ingest.

5. **HITL escalation + kill switch.** A task crosses a policy boundary or
   budget threshold → `AWAITING_HITL`; approver decides in Slack; kill switch
   trip on the same routine demonstrates platform/tenant/routine scopes.

6. **Candidate routine promotion.** The system proposes a new routine from
   observed task traces; it lands in the registry as a candidate; async review
   approves it; the original is **archived before** any hard delete.

---

## Testing strategy (summary)

Unit tests are necessary but **insufficient** for an agentic system. We add:

- **Contract tests** — every Pydantic model round-trips JSON Schema; version
  drift in `Task` / `SpawnLedger` is a build failure.
- **Workflow tests** — Temporal's test harness runs workflows with mocked
  activities; deterministic replay verified.
- **Integration tests** — Slack/Monday/Sheets/tl;dv against sandbox tenants.
- **Dynamic swarm tests** — generate plans, assert wave count, recursion depth,
  ledger ordering, denial reasons (`max_recursion_depth`, `runaway_swarm`).
- **System tests** — full Slack→API→Temporal→tools→Slack scenarios above.
- **Chaos tests** — kill a worker mid-activity, drop a tool to 5xx, expire
  Temporal activity heartbeats, exhaust budgets.
- **Observability tests** — given only the five log streams, reconstruct the
  Task tree and final state; any gap fails the suite.

Full details in [`tests/README.md`](./tests/README.md).

---

## Deployment targets

| Stage | Target |
|---|---|
| Now (POC) | Local Docker Compose. Local Temporal server. |
| Next | **AWS ECS Fargate** for API / workers / Slack / MCP; RDS Postgres (pgvector); self-hosted Temporal cluster on Fargate. |
| Later | Optional Bedrock/Vertex traffic shifting; not Temporal Cloud. |

---

## Boundaries (read these before writing code)

See [`CLAUDE.md`](./CLAUDE.md). The non-negotiables:

- **Temporal orchestrates. Agent SDKs run inside activities, never workflows.**
- **API is the only write surface.** Slack and MCP are clients.
- **Tool Gateway owns all credentials.** Agents are stateless.
- **No raw secrets in prompts.** Ever. Tool Gateway redacts at the boundary.
- **No unledgered spawns.** SpawnLedger row is written before a child runs.
- **Archive before delete.** Routines, releases, and tasks are soft-archived
  first; hard delete is a separate, audited operation.
- **Knowledge Layer is a cache, not a source of truth.** Ground truth lives
  in the external tools/systems of record.
- **Verification is egress-only.** Sufficiency and claim/evidence checks
  happen at output/action boundaries, not continuously mid-stream.
- **Workflow state carries refs, not raw payloads.** `intake_id`,
  `claim_evidence_map_ref`, KL entry IDs, `payload_ref: blob://…`.

---

## Context and Evidence Knowledge Layer

A tenant-scoped substrate that gives agents sufficient, governed,
source-aware context for more capable reasoning. KL provides:

- **Cache** of recent reads from external tools, keyed by
  `(tenant_id, source_system, source_id)`, with optional `content_hash`.
- **Index** for fast retrieval of relevant prior context.
- **Evidence pointers** — every entry carries `evidence_pointer` back to
  the system of record it came from, plus a `freshness` verdict.
- **Append-only versioned writes.** Entries are addressed as
  `kl:{tenant}:{source}/{path}#v{n}`.

LLMs never write KL entries directly. KL is consumed at read time and
referenced at egress through a **`ClaimEvidenceMap`** sidecar that binds
each output claim to one or more evidence refs. The mesh's eight
**deterministic egress guards** then enforce schema, evidence presence,
freshness, source authority, tenancy, tier/policy, and budget — no LLM
in the verification loop.

See `packages/contracts/knowledge_layer.py` and
`packages/contracts/egress.py` for the canonical Pydantic shapes.

---

## Intake contract and S-tier feasibility

Inbound requests from the entry plane produce an **`Intake`** artifact
*before* the Orchestrator creates a Task. Intake runs three cheap checks:

1. **Schema parse** of the canonical intake payload.
2. **Tool-plan lookup** against the routine/release registry.
3. **One S-tier classifier call** producing `feasible | ambiguous |
   infeasible`.

Ambiguous intents produce one disambiguating question. Silent escalation
above S-tier at intake is a bug. Feasibility is decided once at intake —
not re-run mid-stream. The Task references the intake via
`Task.intake_id`.

See `packages/contracts/intake.py`.

---

## Edge security/governance vs mesh execution

The mesh **does not** implement enterprise edge controls. It expects a
generic **edge control contract** in front of it.

| Concern | Owner |
|---|---|
| Identity binding, OAuth/OIDC, session | **Edge layer** |
| Ingress/egress normalization | **Edge layer** |
| Policy preflight, safety, DLP, classification | **Edge layer** |
| Approval UX, audit envelope | **Edge layer** |
| Task decomposition, durable orchestration | **Mesh (this repo)** |
| Knowledge Layer, swarm supervision | **Mesh (this repo)** |
| Routines, releases, evaluator, eight egress guards | **Mesh (this repo)** |
| Tool gateway, credentials, budgets | **Mesh (this repo)** |

[Floodplain](https://github.com/SirFreud/floodplain/tree/rli-0.01)
(branch `rli-0.01`) is **one possible** edge implementation. It is *not*
a required dependency of this POC, and the mesh's egress guards run
defense-in-depth regardless of which edge is in front.

---

## License

TBD. Treat as private until a license is added.
