import os
from pathlib import Path

import pytest

from agent_mesh.services.repository import InMemoryRepository

_MIGRATIONS = (
    "0001_init.sql",
    "0002_self_improvement.sql",
    "0003_tool_call_fields.sql",
    "0004_active_version.sql",
)
_TABLES = (
    # Truncated between tests for isolation. CASCADE handles FK dependents.
    "self_improvement_active_version",
    "ai_bom_snapshots",
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
def agents_stack() -> None:
    """Skip cleanly unless the optional ``.[agents]`` stack is importable.

    Mirrors the ``pg_dsn`` skip-when-unset shape: real-graph orchestration tests
    require LangGraph + Deep Agents, which are optional. We REUSE the load-bearing
    import gates already defined on the orchestrator rather than re-deriving an
    import probe here, so the skip decision and the runtime branch can never drift.
    """
    from agent_mesh.worker import orchestrator

    if not (orchestrator.langgraph_available() and orchestrator.deep_agents_available()):
        pytest.skip("agents extra not installed; real-graph tests require .[agents]")


@pytest.fixture
def sql_repo(pg_dsn: str):
    """A RepositorySQL bound to the test DB, closed after the test."""
    from agent_mesh.services.repository import RepositorySQL

    repo = RepositorySQL(pg_dsn)
    try:
        yield repo
    finally:
        repo.close()


# ---------------------------------------------------------------------------
# Phase-3 shared scaffolding (model gateway / observability). Consumed by
# 03-01 (this plan), 03-02, and 03-03 so those plans own zero overlapping files.
# ---------------------------------------------------------------------------


@pytest.fixture
def live_creds() -> None:
    """Skip cleanly unless real provider credentials are present.

    Mirrors the ``pg_dsn`` skip-when-unset shape so the default ``make test`` run
    never reaches a real provider. ``pytest -m live`` tests depend on this fixture
    (or the ``live`` marker) to gate on credentials being exported.
    """
    if not any(
        os.getenv(var)
        for var in ("ANTHROPIC_API_KEY", "VERTEX_PROJECT_ID", "CF_AIG_WRAPPER_URL")
    ):
        pytest.skip("no provider/gateway creds exported; live tests require them")


class _RecordingRouter:
    """A fake ``litellm.Router`` that records every completion call and returns a
    minimal, deterministic ``ModelResponse``-shaped result.

    Used to PROVE that ``RouterChatLiteLLM`` routes ``.invoke()`` through the held
    Router (defeating the ``litellm.py:558`` ``values["client"] = litellm`` clobber)
    WITHOUT any network or credentials. ``calls`` captures the kwargs each call
    received so a test can assert exactly-one call landed here (not on bare litellm).
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.acalls: list[dict] = []

    def _response(self):
        from litellm import ModelResponse
        from litellm.types.utils import Choices, Message

        return ModelResponse(
            choices=[
                Choices(
                    finish_reason="stop",
                    index=0,
                    message=Message(role="assistant", content="[stub-router] ok"),
                )
            ],
            usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        )

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        return self._response()

    async def acompletion(self, **kwargs):
        self.acalls.append(kwargs)
        return self._response()


@pytest.fixture
def stub_router() -> _RecordingRouter:
    """A call-recording fake Router (no network, no creds)."""
    return _RecordingRouter()


@pytest.fixture
def span_exporter():
    """An OpenTelemetry ``InMemorySpanExporter`` for asserting on emitted spans.

    Consumed by 03-03's trace-wiring tests. Returns a fresh exporter; the test
    wires it into a ``TracerProvider`` via a ``SimpleSpanProcessor``.
    """
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    return InMemorySpanExporter()
