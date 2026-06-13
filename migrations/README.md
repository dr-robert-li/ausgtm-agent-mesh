# Database migrations

Plain SQL migrations for Cloud SQL for PostgreSQL (`australia-southeast1`) with
`pgvector`. Applied in lexical order; each file is idempotent (`IF NOT EXISTS`),
so re-running is safe.

## Apply locally

```bash
# Apply all migrations in lexical order (0001 → 0004)
for f in migrations/0001_*.sql migrations/0002_*.sql migrations/0003_*.sql migrations/0004_*.sql; do
  psql "$DATABASE_URL" -f "$f"
done
```

Current set: `0001_init.sql`, `0002_self_improvement.sql`, `0003_tool_call_fields.sql`,
`0004_active_version.sql`. (Local lanes apply these automatically — see
`tests/conftest.py` and `make test-pg`.)

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
- **Tool execution & approvals:** `tool_calls` (+ `0003` tool-call fields),
  `approval_records`, `proposed_patches`.
- **Governance:** `ai_bom_snapshots`, `budget_ledger`, `gateway_events`.
- **Self-improvement (Option C, `0002` + `0004`):** proposals, evaluations,
  promotions, and the `self_improvement_active_version` pointer.

The embedding dimension is `vector(768)` to suit Vertex/Gemini embeddings; change
it per deployment if a different embedding model is chosen. pgvector indexes
(`ivfflat` / `hnsw`) are intentionally **not** created yet — add them only once
retrieval volume justifies the indexing overhead (per the architecture's
performance guidance).
