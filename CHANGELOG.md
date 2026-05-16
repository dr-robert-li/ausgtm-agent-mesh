# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/dr-robert-li/ausgtm-agent-mesh/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dr-robert-li/ausgtm-agent-mesh/releases/tag/v0.1.0
