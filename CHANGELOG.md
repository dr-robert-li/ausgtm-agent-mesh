# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-05-21

Architecture pivot to off-the-shelf open-source primitives. The runtime is no
longer a bespoke four-plane scaffold maintained in-tree; orchestration logic
moves into **LangGraph**, wrapped by **Temporal** as a thin durable shell. The
reference-arch (`agentic-mesh-reference-arch` `v0.1.3`) contracts and
invariants are unchanged — only the implementation substrate changed.

### Changed

- **Control plane → LangGraph.** The agent state machine, dynamic `Send`
  fan-out, deterministic reducers, the collector fan-in node, the egress
  guards, and interrupt-driven HITL now live in LangGraph.
- **Durable boundary → Temporal shell.** Temporal workflows are deterministic
  shells that invoke a single activity (`run_langgraph_activity`) which runs
  the compiled LangGraph engine. No LLM client or LangGraph import in any
  workflow module. This preserves the reference-arch "no model calls in the
  orchestrator" invariant: the old rule *"agent SDKs run inside activities"*
  becomes *"LangGraph (and all LLM/tool calls) runs inside the activity."*
- **Ingress → FastAPI + FastMCP only.** FastAPI is ingress only; durable work
  moves to Temporal (no `BackgroundTasks` for orchestration). FastMCP is
  mounted on FastAPI. Slack enters over signed HTTP endpoints rather than a
  long-running Socket Mode process.
- **Checkpointing → Postgres `AsyncPostgresSaver`.** LangGraph thread state is
  persisted so interrupts and HITL pause and resume across restarts. This is
  cognitive working memory, kept distinct from the authoritative mesh-state
  schema in the same Postgres instance.
- **LLM egress → Cloudflare AI Gateway.** All model traffic routes through the
  gateway using Cloudflare's documented base URL pattern. LLM egress and tool
  egress are now explicitly separate boundaries (gateway for models, Tool
  Gateway for tools). The model client is the **Claude Agent SDK + Anthropic
  API**, called through the gateway's Anthropic route.
- **Slack ingress hardened.** HMAC signing-secret verification over the raw
  body, timestamp, and versioned basestring with a ≤ 5-minute replay window,
  before any parsing or workflow start.
- **Deterministic fan-in.** Typed reducers plus a collector node merge parallel
  worker outputs and centralize cost/evidence aggregation before guard
  evaluation.

### Removed

- Custom scaffold superseded by the OSS components above: `apps/`, `packages/`
  (`contracts`, `workflows`, `activities`, `model_gateway`, `tool_gateway`,
  `policy`, `registry`, `observability`), `tests/`, `infra/`, `pyproject.toml`,
  and `.env.example`. To be reconstructed on the new stack — see
  [`CLAUDE.md`](./CLAUDE.md) §4 for the build order.
- Direct provider adapters (`anthropic_adapter`, `bedrock_adapter`,
  `vertex_adapter`) superseded by Cloudflare AI Gateway as the egress proxy;
  provider selection is now a gateway/route concern.

### Retained (contract shapes carried into the new stack)

- Reference-arch `v0.1.3` contract shapes survive the pivot and will be
  re-implemented on the OSS stack: `Task` (with `intake_id`, `correlation_id`,
  `claim_evidence_map_ref`, typed `ProvenanceRef`), `Intake` /
  `FeasibilityCheck` (S-tier-only verdicts), `KnowledgeLayerEntry` /
  `EvidencePointer` / `Freshness`, `ClaimEvidenceMap` / `Claim` / `Evidence`,
  `EgressCheckRecord` with the eight-guard `GUARD_ORDER`, `SpawnLedger`,
  `Policy` / `PolicyBudgets` with `evidence_fetch_budget`, `Routine`,
  `HITLDecision`, `EvaluationRecord`.

## [0.1.0] — 2026-05-16

### Added

- Initial scaffold for the local-first Python POC implementation of the
  Agentic Mesh, tracking
  [`agentic-mesh-reference-arch`](https://github.com/dr-robert-li/agentic-mesh-reference-arch)
  `v0.1.2`.
- `README.md` describing purpose, stack, repo structure, local quickstart,
  POC scenarios, testing strategy, and deployment targets (local first,
  AWS ECS Fargate next; not Temporal Cloud).
- `CLAUDE.md` codifying the four-plane architectural pattern and the
  non-negotiable boundaries: Temporal orchestrates, agent SDKs run inside
  activities, Tool Gateway owns credentials, Slack/MCP call the API,
  no raw secrets in prompts, no unledgered spawns, archive before delete.
- `pyproject.toml` with project metadata and dependency declarations
  for FastAPI, uvicorn, Pydantic v2, `temporalio`, `slack_bolt`, `mcp`,
  SQLAlchemy 2.x, `asyncpg`, `psycopg`, `pgvector`, OpenTelemetry,
  `anthropic`, optional `boto3` (Bedrock) and `google-cloud-aiplatform`
  (Vertex), and a `dev` extras group with `pytest`, `pytest-asyncio`,
  `ruff`, `mypy`.
- `.env.example` with required local environment variables for Slack,
  Monday.com, Google Sheets, tl;dv, Anthropic, optional Bedrock and
  Vertex, Postgres, and local Temporal.
- `.gitignore` for Python, virtualenvs, IDE, and local infra artifacts.
- `infra/local/docker-compose.yml` bringing up Postgres 16 with
  `pgvector` and a Temporal auto-setup server with UI.
- Directory scaffold for `apps/{api,slack,mcp,workers}`,
  `packages/{contracts,workflows,activities,model_gateway,tool_gateway,policy,registry,observability}`,
  `infra/{local,aws}`, and the expanded `tests/` tree.
- Placeholder Python entrypoints: FastAPI app stub, Temporal worker stub,
  Slack Bolt app stub, MCP server stub.
- Initial Pydantic contract skeletons for `Task`, `Policy`, `Routine`,
  `SpawnLedger`, `HITLDecision`, and `EvaluationRecord` under
  `packages/contracts/`, modelled on the reference arch's Task contract
  and Swarm Supervisor semantics.
- `tests/README.md` describing the expanded testing strategy (unit,
  contract, workflow, integration, dynamic swarm, system, chaos,
  observability reconstruction).

> Note: the `v0.1.2`→`v0.1.3` alignment work (Intake, Knowledge Layer,
> egress-guard, and `Task` ref-field contracts) was implemented on the custom
> scaffold and then superseded by the `v0.2.0` pivot. Those contract *shapes*
> are retained — see the `v0.2.0` "Retained" section.

[Unreleased]: https://github.com/dr-robert-li/ausgtm-agent-mesh/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/dr-robert-li/ausgtm-agent-mesh/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dr-robert-li/ausgtm-agent-mesh/releases/tag/v0.1.0
