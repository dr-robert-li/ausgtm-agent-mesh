import os
from pathlib import Path

import pytest

from agent_mesh.services.repository import InMemoryRepository

_MIGRATIONS = ("0001_init.sql", "0002_self_improvement.sql")
_TABLES = (
    # Truncated between tests for isolation. CASCADE handles FK dependents.
    "self_improvement_promotions",
    "self_improvement_evaluations",
    "self_improvement_proposals",
    "approval_records",
    "tool_calls",
    "task_events",
    "task_metadata",
    "sessions",
    "tasks",
)


@pytest.fixture
def repo() -> InMemoryRepository:
    """Fresh in-memory repository per test (avoids the process-wide singleton)."""
    return InMemoryRepository()


def _apply_migrations(dsn: str) -> None:
    """Apply 0001/0002 to the test DB. The repo never self-applies migrations;
    the test fixture is the external applier here (psycopg, mirroring psql -f).

    NOTE: TEST_DATABASE_URL MUST point at a pgvector-enabled Postgres (0001 runs
    CREATE EXTENSION vector; IF NOT EXISTS does NOT install it) — e.g. the
    pgvector/pgvector:pg16 image, not a vanilla postgres image.
    """
    import psycopg

    root = Path(__file__).resolve().parents[1] / "migrations"
    with psycopg.connect(dsn, autocommit=True) as conn:
        for name in _MIGRATIONS:
            raw = (root / name).read_text()
            # Strip ``--`` comments (full-line and inline-trailing) to end of
            # line first: their prose contains commas and semicolons that would
            # otherwise corrupt the statement split. Neither migration contains
            # ``--`` inside a string literal, so a plain cut at ``--`` is safe.
            # Both files are plain DDL with no dollar-quoted bodies, so splitting
            # the comment-free text on ';' is safe and sidesteps any
            # multi-statement execute restriction.
            no_comments = "\n".join(
                line.split("--", 1)[0] for line in raw.splitlines()
            )
            for stmt in (s.strip() for s in no_comments.split(";")):
                if stmt:
                    conn.execute(stmt)


def _truncate(dsn: str) -> None:
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("TRUNCATE " + ", ".join(_TABLES) + " CASCADE")


@pytest.fixture
def pg_dsn() -> str:
    """The TEST_DATABASE_URL, or skip the test when it is unset.

    Keeps the default ``make test`` run free of any external dependency
    (TESTING.md: no external deps for tests) while still allowing the SQL-backed
    suite to run against a local pgvector Postgres when the var is provided.
    """
    dsn = os.getenv("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL unset; SQL-backed tests require a local Postgres")
    _apply_migrations(dsn)
    _truncate(dsn)
    return dsn


@pytest.fixture
def sql_repo(pg_dsn: str):
    """A RepositorySQL bound to the test DB, closed after the test."""
    from agent_mesh.services.repository import RepositorySQL

    repo = RepositorySQL(pg_dsn)
    try:
        yield repo
    finally:
        repo.close()
