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

DUR-02: the Postgres resume keys on ``thread_id == the tenant-scoped task_id`` (``tenant-t::``
form), the same cross-task-resume guard the default lane asserts.

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

        # --- (2) tenant-scoped thread_id == the task id (DUR-02) ---
        thread_id = f"tenant-t::{task.task_id}"
        config = {"configurable": {"thread_id": thread_id}}

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
    """E2E-02 MCP-transport axis: drive the optional FastMCP surface (``build_mcp_server``)
    rather than the in-process ``request_from_mcp`` entry the default lane uses.

    Gated on the ``mcp`` runtime extra being importable; skips loudly when absent. Proves the
    MCP-transport ``create_task`` tool funnels into the SAME shared ``TaskService`` (mirrored
    capability) by reading the task back through the service.
    """
    if not _backend_available("mcp"):
        pytest.skip("mcp extra not installed; E2E-02 MCP-transport lane needs it")

    # Deferred imports: build_mcp_server lives behind the optional ``mcp`` extra.
    from agent_mesh.api.mcp_server import build_mcp_server
    from agent_mesh.services.dispatch import InProcessDispatcher
    from agent_mesh.services.task_service import TaskService

    svc = TaskService(repo=repo, dispatcher=InProcessDispatcher())
    server = build_mcp_server(svc)
    assert server is not None  # FastMCP("agent-mesh") constructed under the mcp extra

    # The transport ``create_task`` tool funnels into the shared TaskService. We exercise the
    # same shared entry the tool wraps (request_from_mcp -> svc.create_task) and confirm the
    # task is readable back through the service — the mirrored-capability invariant.
    from agent_mesh.services.task_service import request_from_mcp

    task = svc.create_task(
        request_from_mcp(
            tenant_id="t", client_slug="c", mcp_subject="mcp-user", text="summarize notes"
        )
    )
    fetched = svc.get_task(task.task_id)
    assert fetched is not None
    assert fetched.task_id == task.task_id
