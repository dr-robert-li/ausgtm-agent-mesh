-- Agent Mesh POC — additive ToolCall fields for Phase 4 tool adapters.
-- Region: australia-southeast1 (durable store stays in Australia).
--
-- Phase 4 wires the Tool Gateway to real adapters, so the tool_calls record
-- grows three additive columns (audit item D). This migration is ADDITIVE ONLY:
-- it never rewrites the P1-era contract or existing rows, and every column has a
-- safe default so historical rows remain valid.
--
--   * integration_style  - how the call was routed (direct_api / aggregate_mcp /
--                           nango_aggregator / composio_aggregator / mcp_server).
--   * schema_validation   - JSON-Schema boundary outcome (D-06):
--                           'ok' | 'input_rejected' | 'output_quarantined'.
--   * is_read             - True for non-gated reads, False for gated writes.
--
-- Follows the same conventions as 0001_init.sql / 0002_self_improvement.sql:
--   * Idempotent: ADD COLUMN IF NOT EXISTS so it can be re-applied.
--   * Defaults keep existing rows valid (no backfill required).

ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS integration_style TEXT;
ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS schema_validation TEXT;
ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS is_read BOOLEAN NOT NULL DEFAULT false;
