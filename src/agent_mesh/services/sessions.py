"""Session helpers.

Sessions hold operational conversation state and are kept separate from
retrieval evidence (see the migrations). For the in-memory POC repository there
is no dedicated session store, so ``ensure_session`` simply derives/echoes a
stable session id from the request. A Postgres implementation would upsert into
the ``sessions`` table here.
"""

from __future__ import annotations

from uuid import uuid4

from agent_mesh.contracts.models import TaskRequest
from agent_mesh.services.repository import Repository


def ensure_session(repo: Repository, request: TaskRequest) -> str:  # noqa: ARG001
    """Return an existing session id or mint a new one.

    ``repo`` is accepted so a Postgres-backed implementation can upsert the
    session row; the in-memory POC keeps session state implicit on the task.
    """
    if request.session_id:
        return request.session_id
    return f"session-{uuid4().hex}"
