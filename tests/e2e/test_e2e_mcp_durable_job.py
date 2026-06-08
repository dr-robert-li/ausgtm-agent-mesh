"""E2E-02 default-lane proof (ROADMAP SC-2): an MCP request drives a long-running
checkpointed mesh job through the PRODUCTION Worker/orchestrator wiring, and its artifact
SURVIVES a true durable restart-resume.

D-03 (corrected): the MCP entry is in-process ``request_from_mcp -> TaskService.create_task``
— there is NO ``/mcp`` HTTP route (app.py exposes only /healthz, /v1/tasks, /slack/events,
/v1/approvals; ``mcp_server.build_mcp_server`` is FastMCP behind the ``mcp`` extra). The
optional MCP-transport variant lives in ``test_e2e_mcp_durable_job_live.py``.

CR-01 (this rewrite): the durability proof drives the REAL production path rather than an
inline compiled graph. The earlier version compiled and invoked the graph with an inline
saver directly, so it proved only the SqliteSaver drop-then-reopen PRIMITIVE — not the
production durable wiring — and keyed on an invented thread_id production never writes. This
test now
injects a FILE-backed ``SqliteSaver`` through the documented
``orchestrator.set_checkpointer_override`` seam (the one ``_select_checkpointer`` returns
first) and drives ``Worker.process`` end to end on BOTH legs: the pause leg routes through
``run_mesh -> _run_langgraph -> _select_checkpointer -> _graph_config`` and parks the task in
AWAITING_APPROVAL at the write_gate interrupt; the resume leg routes through
``_resume_after_approval -> resume_mesh -> Command(resume=True)`` on the same production
config. Production ``orchestrator._graph_config`` is unchanged — the test is test-side and
seam-driven only.

D-04: durability is the REAL checkpointer mechanism, proven in the DEFAULT lane via the
sqlite-backed drop-then-reopen-same-store fallback — never an in-memory connection target
(that loses exactly what a restart loses). The "restart" is the same simulated process-death
``test_checkpointer_resume.py`` uses: drive the run to the ``write_gate`` ``interrupt()`` (a
paused long run), DROP the saver + close the connection, reopen a FRESH saver on the SAME
file-backed store, and drive the resume through the production worker path. The run resumes
from the persisted checkpoint and the reviewer artifact survives.

Production key (DUR-02 scope, stated honestly): the checkpoint is written and read under the
BARE production ``thread_id`` sourced from ``orchestrator._graph_config(task)`` — which is
``task.task_id`` verbatim. Bare is safe because the checkpointer keys purely on the
``thread_id`` string and ``task_id`` is a globally-unique uuid4 hex
(``contracts/models.py`` ``_new_id -> uuid4().hex``), so no two tasks in any tenant can
collide on the key. This single-task test proves DURABLE RESUME THROUGH THE PRODUCTION
WIRING (the actual CR-01 gap); it does NOT by itself prove DUR-02 cross-task isolation —
that would need a two-task test.

The artifact-survival proof is DISCRIMINATING: it reads the REOPENED checkpointer under the
production config and goes RED on checkpoint loss (empty store / in-memory target), so it is
NOT a ``state == completed`` tautology. Empirically the worker reaches COMPLETED even when
the checkpoint is lost (the approved write replays from the AWAITING_APPROVAL stash), so the
two reopened-checkpoint reads — the pre-resume survival read and the post-resume consumption
read — are what make the proof non-tautological.

GATING (PATTERNS SP-2): this module carries NO ``live`` marker — it is the sqlite fallback in
``make test``, gated only on the ``agents_stack`` fixture (langgraph + deepagents importable)
plus the optional ``langgraph-checkpoint-sqlite`` backend. The Postgres lane and the
MCP-transport entry are exercised by the opt-in companion module.
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
    """E2E-02: an in-process MCP request creates a task, ``Worker.process`` drives a
    checkpointed mesh job that pauses at the write gate, the run survives a simulated process
    restart on a FILE-backed sqlite checkpoint, and the production resume path consumes the
    durable checkpoint to completion.

    The whole flow runs through the production Worker/orchestrator wiring via the
    ``orchestrator.set_checkpointer_override`` seam (file-backed ``SqliteSaver``, never an
    in-memory connection target); the checkpoint is keyed on the BARE production thread_id
    from ``orchestrator._graph_config(task)``. The artifact-survival assertions read the
    REOPENED store and go red on checkpoint loss. Skips loudly when the sqlite backend is
    absent.
    """
    if not _backend_available("langgraph.checkpoint.sqlite"):
        pytest.skip("langgraph-checkpoint-sqlite not installed; E2E-02 default lane needs it")

    # Deferred imports: keep this module COLLECTABLE (and thus skippable, not errored) in a
    # minimal env where langgraph is absent. The skip gates above run first.
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    from agent_mesh.contracts.enums import ApprovalDecision
    from agent_mesh.services.dispatch import InProcessDispatcher
    from agent_mesh.services.task_service import TaskService, request_from_mcp
    from agent_mesh.worker import orchestrator
    from agent_mesh.worker.runner import Worker

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

    # --- (2) file-backed sqlite store (never an in-memory connection target) ---
    db_path = str(tmp_path / "checkpoints.sqlite")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    conn2 = None
    try:
        # Inject the saver via the documented production seam: ``_select_checkpointer``
        # returns the override FIRST, so the whole production path now persists to this file.
        orchestrator.set_checkpointer_override(saver)

        # --- (3) the BARE production key, sourced from production _graph_config(task) ---
        cfg = orchestrator._graph_config(task)
        assert cfg["configurable"]["thread_id"] == task.task_id  # bare uuid4 key, no prefix

        # --- (4) PAUSE leg through production: Worker.process -> run_mesh -> _run_langgraph
        # -> _select_checkpointer (returns the override) -> _graph_config; writes the
        # checkpoint under the bare task.task_id and parks the task at the write gate. ---
        w = Worker(repo=repo)
        assert w.process(task.task_id) == "awaiting_approval"
        assert saver.get_tuple(cfg) is not None  # checkpoint persisted on the pause leg

        # --- (5) simulate PROCESS DEATH: clear the override, drop the saver, close conn ---
        orchestrator.set_checkpointer_override(None)
        del saver
        conn.close()

        # --- (6) reopen a FRESH saver on the SAME file and re-inject via the seam ---
        conn2 = sqlite3.connect(db_path, check_same_thread=False)
        saver2 = SqliteSaver(conn2)
        orchestrator.set_checkpointer_override(saver2)

        # DISCRIMINATING pre-resume survival read: the persisted checkpoint is READABLE from
        # the reopened store under the production key, and the reviewer ARTIFACT survived the
        # restart. This flips RED on checkpoint loss (empty store / in-memory target) — it is
        # what makes the proof non-tautological (state == completed alone does not).
        survived = saver2.get_tuple(cfg)
        assert survived is not None
        assert survived.checkpoint["channel_values"].get("review")  # artifact survived restart

        # --- (7) RESUME leg through production: approve via the shared ledger, then
        # Worker.process -> _resume_after_approval -> resume_mesh -> Command(resume=True) on
        # _graph_config(task) — the production resume path on the bare key. ---
        (record,) = repo.list_approvals(task.task_id, "t")
        svc.submit_approval_decision(
            record.approval_record_id, ApprovalDecision.APPROVED, "mcp:svc", "mcp"
        )
        assert w.process(task.task_id) == "completed"

        # --- (7b) DISCRIMINATING resume-CONSUMPTION read (completion alone is NOT enough):
        # the resume actually CONSUMED the durable checkpoint rather than stash-completing on
        # a fresh graph. Empirically True for the same-file restart but None for an
        # empty-store / in-memory reopen (the fresh graph never resumed). The step-6 read
        # proves SURVIVAL; this read proves CONSUMPTION — both are kept (they flip red on
        # different failures). ---
        consumed = saver2.get_tuple(cfg)
        assert consumed.checkpoint["channel_values"].get("decision") is True
    finally:
        # Teardown hygiene: the override is a module global that _select_checkpointer returns
        # first — a leak would corrupt every later agents-gated test. Always clear it and
        # close both connections (sqlite3 close() is idempotent, so a double-close on the
        # already-closed original connection is safe).
        orchestrator.set_checkpointer_override(None)
        if conn2 is not None:
            conn2.close()
        conn.close()
