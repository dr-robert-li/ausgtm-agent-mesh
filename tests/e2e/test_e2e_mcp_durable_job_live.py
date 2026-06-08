"""E2E-02 opt-in variant: the two axes the default lane (sqlite, in-process MCP) cannot
exercise — the REAL Postgres checkpointer restart-resume and the MCP-TRANSPORT entry.

This module mirrors ``test_e2e_mcp_durable_job.py`` on the Postgres/transport axis:

* ``test_e2e_postgres_durable_restart`` — the REAL PostgresSaver restart-resume, routed
  through the PRODUCTION ``orchestrator._select_checkpointer()`` / ``close_checkpointer()``
  lifecycle (NOT an inline saver), exactly as ``test_checkpointer_resume.py:86-125`` does.
  Gated on ``pg_dsn`` (TEST_DATABASE_URL) + ``_backend_available("langgraph.checkpoint.
  postgres")``. NO ``live`` marker — it is DSN-gated, not creds-gated.
* ``test_e2e_mcp_transport_create_task`` — the optional MCP-TRANSPORT entry driving
  ``build_mcp_server(service)`` tools (the FastMCP surface behind the ``mcp`` extra),
  gated on the ``mcp`` runtime extra being importable. Skips loudly when absent.

Both axes skip loudly and named when their dependency is unavailable, so the default suite
stays green when neither is present.

NO module-level ``pytestmark`` / ``live`` marker is set here (intentionally — see below): the
D-03-corrected body forbids a ``live`` marker on the Postgres lane (it is TEST_DATABASE_URL-
gated, not creds-gated), and a module-wide ``pytestmark = pytest.mark.live`` would deselect
the Postgres lane from ``make test -m "not live"`` so it could never run even with a DSN set.
Gating is therefore per-function via the ``pg_dsn`` / ``_backend_available`` skip guards
below, not a module ``pytestmark``.

DUR-02 (scope, stated honestly): the Postgres resume keys on the BARE production thread_id
sourced from ``orchestrator._graph_config(task)`` — which is ``task.task_id`` verbatim. Bare
is safe because the checkpointer keys purely on the thread_id string and ``task_id`` is a
globally-unique uuid4 hex, so no two tasks (in any tenant) collide on the key. This is the
same production-key contract the default lane asserts.

T-07-06: the DSN is sourced from the env (``TEST_DATABASE_URL``) only in this opt-in lane and
is never logged; the default lane has no DB at all.
"""

from __future__ import annotations

import importlib.util

import pytest


def _backend_available(module: str) -> bool:
    """True when a langgraph checkpoint backend (or the ``mcp`` extra) is importable.

    Only ever reached after ``agents_stack`` (Postgres lane) confirms the parent
    ``langgraph`` package imports, so ``find_spec`` cannot raise on a missing parent.
    """
    return importlib.util.find_spec(module) is not None


# A WRITE-trigger prompt so the graph pauses at the write_gate interrupt — the paused long
# run that the restart resumes.
_PROMPT = "create a new HubSpot deal for ACME Corp"


def test_e2e_postgres_durable_restart(agents_stack, pg_dsn, monkeypatch):
    """E2E-02 Postgres lane: the same MCP-request -> checkpointed-job -> surviving-artifact
    proof, but against a REAL PostgresSaver routed through the PROD checkpointer lifecycle.

    The "process restart" is simulated by ``close_checkpointer()`` (drops the cached
    connection) followed by a fresh ``_select_checkpointer()`` on the SAME DSN — exercising
    the production construction + cache + close lifecycle, never an inline saver. Skips
    loudly when the postgres backend is absent.
    """
    if not _backend_available("langgraph.checkpoint.postgres"):
        pytest.skip("langgraph-checkpoint-postgres not installed; E2E-02 Postgres lane needs it")

    # Deferred imports: keep this module COLLECTABLE in a minimal env where langgraph is
    # absent (so it SKIPS, never errors at collection). The skip gates above run first.
    from langgraph.types import Command

    from agent_mesh.services.dispatch import InProcessDispatcher
    from agent_mesh.services.repository import RepositorySQL
    from agent_mesh.services.task_service import TaskService, request_from_mcp
    from agent_mesh.worker import orchestrator
    from agent_mesh.worker.graph import build_graph

    # The production checkpointer selects on DATABASE_URL; point it at the test DSN.
    monkeypatch.setenv("DATABASE_URL", pg_dsn)

    # --- (1) MCP request creates the task in-process (the same shared TaskService entry) ---
    repo = RepositorySQL(pg_dsn)
    try:
        svc = TaskService(repo=repo, dispatcher=InProcessDispatcher())
        task = svc.create_task(
            request_from_mcp(
                tenant_id="t",
                client_slug="c",
                mcp_subject="svc",
                text=_PROMPT,  # write-trigger verb -> write_gate pauses
            )
        )

        # --- (2) BARE production thread_id, sourced from production _graph_config (DUR-02) ---
        config = orchestrator._graph_config(task)
        assert config["configurable"]["thread_id"] == task.task_id  # bare uuid4 key, no prefix

        try:
            # --- (3) run to the interrupt via the PROD checkpointer path ---
            saver = orchestrator._select_checkpointer()  # builds PostgresSaver from DATABASE_URL
            assert saver is not None
            # Cached: a second selection reuses the same connection (no per-task leak).
            assert orchestrator._select_checkpointer() is saver
            graph = build_graph().compile(checkpointer=saver)
            paused = graph.invoke({"prompt": _PROMPT, "task_id": task.task_id}, config)
            assert "__interrupt__" in paused
            assert paused["__interrupt__"][0].value["proposed_writes"]

            # --- (4) simulated restart: close the cached saver, re-select on the SAME DSN ---
            orchestrator.close_checkpointer()
            saver2 = orchestrator._select_checkpointer()
            assert saver2 is not None
            assert saver2 is not saver, "close_checkpointer must drop cache; new saver expected"
            graph2 = build_graph().compile(checkpointer=saver2)
            resumed = graph2.invoke(Command(resume=True), config)
            assert "__interrupt__" not in resumed
            assert resumed.get("decision") is True
            assert resumed.get("review")  # NON-EMPTY artifact survived the real restart
        finally:
            orchestrator.close_checkpointer()
    finally:
        repo.close()


def test_e2e_mcp_transport_create_task(repo):
    """E2E-02 MCP-transport axis (WR-01): drive the REGISTERED FastMCP ``create_task`` tool
    via the in-process ``call_tool`` harness, rather than re-deriving the in-process
    ``request_from_mcp`` entry the default lane uses.

    Gated on the ``mcp`` runtime extra being importable; skips loudly when absent. Builds the
    server over a shared ``TaskService``, invokes the registered transport tool, and reads the
    created task back THROUGH THE SAME SERVICE — so a broken/misrouted tool registration now
    fails this test (the prior construction-only assertion could not).
    """
    if not _backend_available("mcp"):
        pytest.skip("mcp extra not installed; E2E-02 MCP-transport lane needs it")

    # Deferred imports: build_mcp_server lives behind the optional ``mcp`` extra.
    import asyncio

    from agent_mesh.api.mcp_server import build_mcp_server
    from agent_mesh.services.dispatch import InProcessDispatcher
    from agent_mesh.services.task_service import TaskService

    svc = TaskService(repo=repo, dispatcher=InProcessDispatcher())
    server = build_mcp_server(svc)

    # Invoke the REGISTERED transport tool in-process. ``FastMCP.call_tool`` is an async
    # coroutine returning a ``(content_blocks, structured_dict)`` tuple; the structured dict
    # carries ``{"task_id", "state"}`` from the registered ``create_task`` tool body.
    result = asyncio.run(server.call_tool("create_task", {"prompt": "summarize notes"}))
    structured = result[1]
    task_id = structured["task_id"]

    # The transport tool funnels into the SHARED TaskService: read the task back through the
    # service to prove the mirrored-capability invariant end to end across the tool boundary.
    fetched = svc.get_task(task_id)
    assert fetched is not None
    assert fetched.task_id == task_id
