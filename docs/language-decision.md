# Language Decision: Python-First, TypeScript at the Edge

## Decision

The agent mesh is implemented **Python-first**. TypeScript is used **only at the
edge** — specifically the Cloudflare Worker that wraps the AI Gateway
(`cloudflare/ai-gateway-wrapper/`), where the runtime is V8/Workers and TS is the
native choice.

Everything else — contracts, ingress (Slack/MCP/API), the shared task service,
the dispatch layer, the AG2 worker, the prompt-to-code sandbox, and the tooling —
is Python.

## Why Python for the core

- **AG2 is Python-native.** The multi-agent execution layer (group-chat /
  blackboard orchestration, code-writer/executor roles) is a Python library. A
  Python core avoids a cross-language boundary on the hottest path.
- **LiteLLM Proxy is Python-backed.** The model control plane (routing,
  cascades, budgets, token caps) is configured and extended in Python.
- **Official MCP Python SDK** supports servers, clients, and transports
  (including Streamable HTTP) with Pydantic structured output — the same Pydantic
  v2 models we use for the task contract serve double duty as MCP tool schemas.
- **Slack Bolt for Python** gives first-class Events API + signature handling.
- **One contract source of truth.** Pydantic v2 models define the task
  lifecycle, approvals, tool calls, evidence, AI-BOM, and budget events, and JSON
  Schema is *exported* from them (`agent_mesh.contracts.export_schemas`) so
  non-Python consumers (the Worker, MCP clients, dashboards) share the contract
  without duplicating definitions.

## Why TypeScript only at the edge

- The Cloudflare AI Gateway wrapper runs on the Workers runtime, where TS/JS is
  the supported language. Wrangler tooling expects it.
- The edge wrapper has a narrow job (forward model traffic, attach metadata) and
  consumes the JSON Schema exported from the Python contracts, so the language
  split does not fragment the contract.

## Pros / Cons

| | Python-first core | Alternative: TS-first core |
| :-- | :-- | :-- |
| AG2 orchestration | Native, no FFI | No first-class AG2; reimplement or bridge |
| LiteLLM | Native config/extension | Subprocess/HTTP bridge |
| MCP SDK | Official, Pydantic-integrated | TS SDK exists but loses Pydantic reuse |
| Slack | Bolt for Python | Bolt for JS (fine) |
| Contract reuse | Pydantic → JSON Schema export | Would still need schema export |
| Edge worker | TS (unavoidable) | TS (native) |
| Team fit | Stronger Python | — |

Trade-off accepted: a two-language repo. Mitigated by keeping the boundary thin
(only the edge worker is TS) and by exporting one canonical JSON Schema from the
Python contracts so both sides agree.

## Repo layout implication

```
src/agent_mesh/            # Python core (importable as `agent_mesh`)
  contracts/               # Pydantic models, enums, lifecycle, schema export
  services/                # repository, dispatch, sessions, task_service, approvals
  api/                     # FastAPI app, Slack verify, MCP server
  worker/                  # orchestrator (AG2 stub), runner, budget, main
  sandbox/                 # prompt-to-code executor
  tools/                   # tool gateway + tool-pack loader
schemas/                   # exported JSON Schema (contracts/) + sample tool schemas
migrations/                # Cloud SQL Postgres + pgvector SQL
config/litellm.config.yaml # LiteLLM routing/budgets via Cloudflare AI Gateway
cloudflare/ai-gateway-wrapper/  # TS edge worker (the only TypeScript)
docker/                    # api / worker / code-executor images
scripts/                   # idempotent gcloud + wrangler deploy scripts
tests/                     # contract, approval-gating, import, slack-verify, smoke
```

The Python package installs with optional extras (`runtime`, `agents`, `dev`) so
the contract/schema layer and tests run in a minimal environment while the
worker/ingress images install the full set. Heavy deps (`ag2`, `google-cloud-pubsub`,
`mcp`) are lazy-imported and degrade to stubs so the package stays importable
without them.
