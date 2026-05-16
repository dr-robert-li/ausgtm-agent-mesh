-- Run on first boot of the app Postgres container.
-- Idempotent: safe to re-run.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
