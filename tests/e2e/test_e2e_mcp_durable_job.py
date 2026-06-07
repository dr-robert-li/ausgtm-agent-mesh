"""E2E-02 default-lane proof (ROADMAP SC-2): an MCP request drives a long-running
checkpointed mesh job whose artifact SURVIVES a true durable restart-resume.

D-03 (corrected): the MCP entry is in-process ``request_from_mcp -> TaskService.create_task``
— there is NO ``/mcp`` HTTP route (app.py exposes only /healthz, /v1/tasks, /slack/events,
/v1/approvals; ``mcp_server.build_mcp_server`` is FastMCP behind the ``mcp`` extra). The
optional MCP-transport variant lives in ``test_e2e_mcp_durable_job_live.py``.

D-04: durability is the REAL Postgres checkpointer mechanism, proven here in the DEFAULT
lane via the sqlite-backed drop-then-reopen-same-store fallback — NEVER an in-memory saver.
The "restart" is the same simulated process-death used by ``test_checkpointer_resume.py``:
invoke the graph to the ``write_gate`` ``interrupt()`` (a paused long run), DROP the saver +
graph + connection, reopen a FRESH saver on the SAME file-backed store, and dispatch
``Command(resume=True)`` on the SAME tenant-scoped ``thread_id``. The run resumes from the
persisted checkpoint and the reviewer artifact survives.

DUR-02: the resume always keys on ``thread_id == the tenant-scoped task_id`` (``tenant-t::``
form), never a bare thread_id — that is what scopes a checkpoint to one task and blocks
cross-task resume (T-07-05).

GATING (PATTERNS SP-2): this module carries NO ``live`` marker — it is the sqlite fallback
in ``make test``, gated only on the ``agents_stack`` fixture (langgraph + deepagents
importable) plus the optional ``langgraph-checkpoint-sqlite`` backend. The Postgres lane and
the MCP-transport entry are exercised by the opt-in companion module.

NOTE: this leg is graph-level (the resume runs the compiled graph directly via
``Command(resume=True)``); it does NOT drive an HTTP route and does NOT rebind
``app_module._service`` (SP-1 does not apply to E2E-02).
"""

from __future__ import annotations

import importlib.util

import pytest


def _backend_available(module: str) -> bool:
    """True when a langgraph checkpoint backend is importable.

    The ``agents_stack`` fixture only checks langgraph + deepagents; the checkpoint
    backends (``langgraph-checkpoint-sqlite`` / ``-postgres``) are separately optional.
    Gate on actual backend importability so this test SKIPS cleanly where the backend is
    absent and RUNS (proving E2E-02) where it is installed.

    This is only ever reached AFTER the ``agents_stack`` fixture has confirmed the parent
    ``langgraph`` package is importable, so ``find_spec`` cannot raise on a missing parent.
    """
    return importlib.util.find_spec(module) is not None


# A WRITE-trigger prompt so the graph pauses at the write_gate interrupt — that pause IS the
# long-running checkpointed job that the restart resumes.
_PROMPT = "create a new HubSpot deal for ACME Corp"


def test_e2e_mcp_request_survives_durable_restart(agents_stack, repo, tmp_path):
    """E2E-02: an in-process MCP request creates a task, drives a checkpointed mesh job that
    pauses at the write gate, survives a simulated process restart on a FILE-backed sqlite
    checkpoint, and resumes to return a NON-EMPTY artifact.

    File-backed ``SqliteSaver`` on a tempfile (NEVER ``:memory:``); resume on the SAME
    tenant-scoped ``thread_id`` (DUR-02). Skips loudly when the sqlite backend is absent.
    """
    if not _backend_available("langgraph.checkpoint.sqlite"):
        pytest.skip("langgraph-checkpoint-sqlite not installed; E2E-02 default lane needs it")

    # Deferred imports: keep this module COLLECTABLE (and thus skippable, not errored) in a
    # minimal env where langgraph is absent. The skip gates above run first.
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command

    from agent_mesh.services.dispatch import InProcessDispatcher
    from agent_mesh.services.task_service import TaskService, request_from_mcp
    from agent_mesh.worker.graph import build_graph

    # --- (1) MCP request creates the task IN-PROCESS (D-03 corrected: no /mcp HTTP route) ---
    svc = TaskService(repo=repo, dispatcher=InProcessDispatcher())
    task = svc.create_task(
        request_from_mcp(
            tenant_id="t",
            client_slug="c",
            mcp_subject="svc",
            text=_PROMPT,  # write-trigger verb -> write_gate pauses
        )
    )

    # --- (2) tenant-scoped thread_id == the task id (DUR-02), never a bare thread_id ---
    thread_id = f"tenant-t::{task.task_id}"
    config = {"configurable": {"thread_id": thread_id}}

    db_path = str(tmp_path / "checkpoints.sqlite")  # file-backed, NOT :memory:

    # --- (3) run to the interrupt (paused long run), then simulate process death ---
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    graph = build_graph().compile(checkpointer=saver)
    paused = graph.invoke({"prompt": _PROMPT, "task_id": task.task_id}, config)
    assert "__interrupt__" in paused  # the write_gate interrupt fired -> run is paused
    assert paused["__interrupt__"][0].value["proposed_writes"]  # carries the gated write
    # DROP the saver + graph + connection: simulated process restart.
    del graph
    del saver
    conn.close()

    # --- (4) fresh saver on the SAME file + fresh graph; resume on the SAME thread_id ---
    conn2 = sqlite3.connect(db_path, check_same_thread=False)
    saver2 = SqliteSaver(conn2)
    try:
        graph2 = build_graph().compile(checkpointer=saver2)
        resumed = graph2.invoke(Command(resume=True), config)
        # Resumed from the persisted checkpoint: the interrupt cleared, the gate recorded the
        # verified decision, and the reviewer ARTIFACT survived the restart in the checkpoint.
        assert "__interrupt__" not in resumed
        assert resumed.get("decision") is True
        assert resumed.get("review")  # NON-EMPTY artifact survived the restart-resume
    finally:
        conn2.close()
