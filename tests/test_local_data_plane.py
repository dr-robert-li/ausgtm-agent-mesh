"""DSN-gated DDL schema-assertion test for the local data plane (LDATA-03).

Proves that migrations 0003 and 0004 land in the LIVE migrated Postgres schema
(no other test asserts this at the DDL layer — only at the Pydantic-contract and
repository layers). Rides the ``pg_dsn`` fixture (conftest), which loud-skips on
unset ``TEST_DATABASE_URL``, applies 0001->0004, and truncates — so this file
collects under plain ``make test`` and skips cleanly there, while running for
real under ``make test-pg`` when a local pgvector DSN is exported.

psycopg is imported inside the test body (not at module scope) so collection
stays clean on any interpreter without the dependency — the ``pg_dsn`` setup
skips before the body runs when the DSN is unset. This mirrors the conftest
convention of importing psycopg inside functions.
"""


def test_migrated_schema_has_0003_and_0004_objects(pg_dsn: str) -> None:
    """The migrated schema contains the 0003 tool_calls columns, the 0004 tables,
    and is reachable. Subset (<=) assertions — the migrated schema has many more
    objects; assert the specific 0003/0004 objects are PRESENT, not exclusive.
    """
    import psycopg

    with psycopg.connect(pg_dsn) as conn:
        # 0003 (migrations/0003_tool_call_fields.sql): additive tool_calls columns.
        cols = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'tool_calls'"
            ).fetchall()
        }
        assert {"integration_style", "schema_validation", "is_read"} <= cols

        # 0004 (migrations/0004_active_version.sql): new tables in schema public.
        tabs = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ).fetchall()
        }
        assert {"self_improvement_active_version", "ai_bom_snapshots"} <= tabs

        # Reachability.
        assert conn.execute("SELECT 1").fetchone()[0] == 1
