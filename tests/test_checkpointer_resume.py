"""ORCH-02: a (simulated >60-min) run resumes from its durable checkpoint after a
process restart — proven WITHOUT a purely in-memory saver and WITHOUT a real timer.

The restart is simulated by the same drop-then-reopen-same-store mechanism the
``test_repository_sql`` restart-survival test uses: invoke the graph to the write_gate
``interrupt()`` (a paused long run), DROP the saver + graph + connection (simulated
process death), open a FRESH saver on the SAME store + a fresh compiled graph, and
dispatch ``Command(resume=...)`` on the SAME ``thread_id``. The run resumes from the
persisted checkpoint and reaches terminal.

* ``test_resume_after_restart_sqlite`` — agents-stack + sqlite-backend gated, no DB
  required. File-backed ``SqliteSaver`` on a tempfile (NEVER ``:memory:``).
* ``test_resume_after_restart_postgres`` — TEST_DATABASE_URL-gated. The same drop/reopen
  proof against a real ``PostgresSaver``.

DUR-02: the resume always uses ``thread_id == the tenant-scoped task_id``, never a bare
thread_id (the checkpointer keys on thread_id only, so this is what scopes a checkpoint
to one task and blocks cross-task resume — T-02-02-03).
"""

from __future__ import annotations

import importlib.util

import pytest

from agent_mesh.worker.graph import build_graph


def _backend_available(module: str) -> bool:
    """True when a langgraph checkpoint backend is importable.

    The conftest ``agents_stack`` fixture only checks langgraph + deepagents; the
    checkpoint backends (``langgraph-checkpoint-sqlite`` / ``-postgres``) are separately
    optional. Gate on actual backend importability so these tests SKIP cleanly where the
    backend is absent and RUN (proving ORCH-02) where it is installed."""
    return importlib.util.find_spec(module) is not None


# Tenant-scoped task id used as the LangGraph thread_id (DUR-02).
_THREAD_ID = "tenant-t::task-orch02"
_PROMPT = "create a new HubSpot deal for ACME Corp"  # mutating verb -> write_gate pauses


def test_resume_after_restart_sqlite(agents_stack, tmp_path):
    """File-backed SqliteSaver restart-sim: pause at interrupt, drop, reopen SAME file,
    resume on SAME thread_id, reach terminal — no purely in-memory saver, no real timer."""
    if not _backend_available("langgraph.checkpoint.sqlite"):
        pytest.skip("langgraph-checkpoint-sqlite not installed")

    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command

    db_path = str(tmp_path / "checkpoints.sqlite")  # file-backed, NOT :memory:
    config = {"configurable": {"thread_id": _THREAD_ID}}  # DUR-02 tenant-scoped task id

    # --- run to the interrupt (paused long run), then simulate process death ---
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    graph = build_graph().compile(checkpointer=saver)
    paused = graph.invoke({"prompt": _PROMPT}, config)
    assert "__interrupt__" in paused  # the write_gate interrupt fired -> run is paused
    assert paused["__interrupt__"][0].value["proposed_writes"]  # carries the gated write
    # DROP the saver + graph + connection: simulated process restart.
    del graph
    del saver
    conn.close()

    # --- fresh saver on the SAME file + fresh graph; resume on the SAME thread_id ---
    conn2 = sqlite3.connect(db_path, check_same_thread=False)
    saver2 = SqliteSaver(conn2)
    try:
        graph2 = build_graph().compile(checkpointer=saver2)
        resumed = graph2.invoke(Command(resume=True), config)
        # Resumed from the persisted checkpoint: the interrupt is cleared and the gate
        # recorded the verified decision -> terminal.
        assert "__interrupt__" not in resumed
        assert resumed.get("decision") is True
        assert resumed.get("review")  # reviewer output survived the restart in the checkpoint
    finally:
        conn2.close()


def test_resume_after_restart_postgres(agents_stack, pg_dsn):
    """The same drop/reopen restart-sim against a real PostgresSaver on the test DSN."""
    if not _backend_available("langgraph.checkpoint.postgres"):
        pytest.skip("langgraph-checkpoint-postgres not installed")

    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.types import Command

    config = {"configurable": {"thread_id": _THREAD_ID}}  # DUR-02 tenant-scoped task id

    # --- run to the interrupt, then simulate process death (exit the saver CM) ---
    with PostgresSaver.from_conn_string(pg_dsn) as saver:
        saver.setup()  # idempotent, library-owned sibling schema
        graph = build_graph().compile(checkpointer=saver)
        paused = graph.invoke({"prompt": _PROMPT}, config)
        assert "__interrupt__" in paused
        assert paused["__interrupt__"][0].value["proposed_writes"]
    # The CM exit drops the connection: simulated restart.

    # --- fresh saver on the SAME DSN + fresh graph; resume on the SAME thread_id ---
    with PostgresSaver.from_conn_string(pg_dsn) as saver2:
        graph2 = build_graph().compile(checkpointer=saver2)
        resumed = graph2.invoke(Command(resume=True), config)
        assert "__interrupt__" not in resumed
        assert resumed.get("decision") is True
        assert resumed.get("review")
