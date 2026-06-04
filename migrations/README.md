# Database migrations

Plain SQL migrations for Cloud SQL for PostgreSQL (`australia-southeast1`) with
`pgvector`. Applied in lexical order; each file is idempotent (`IF NOT EXISTS`),
so re-running is safe.

## Apply locally

```bash
psql "$DATABASE_URL" -f migrations/0001_init.sql
```

## Apply against Cloud SQL

Use the Cloud SQL Auth Proxy, then run `psql` against the proxied connection.
See `RUNBOOK.md` for provisioning. The bootstrap script creates the instance and
database; migrations are applied as a separate step before first deploy.

## Schema separation (intentional)

- **Operational state:** `tasks`, `task_metadata`, `task_events`, `sessions`,
  `session_summaries`.
- **Reusable memory:** `memory_chunks`.
- **Retrieval / tool evidence (kept separate from the above):**
  `retrieval_document_chunks`, `tool_evidence_chunks`.
- **Tool execution & approvals:** `tool_calls`, `approval_records`,
  `proposed_patches`.
- **Governance:** `ai_bom_snapshots`, `budget_ledger`, `gateway_events`.

The embedding dimension is `vector(768)` to suit Vertex/Gemini embeddings; change
it per deployment if a different embedding model is chosen. pgvector indexes
(`ivfflat` / `hnsw`) are intentionally **not** created yet — add them only once
retrieval volume justifies the indexing overhead (per the architecture's
performance guidance).
