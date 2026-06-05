"""Real LangGraph ``StateGraph`` topology for the supervisor mesh (ORCH-01 + ORCH-03).

This module owns the orchestration graph: four declared role nodes
(planner -> researcher/tool-router -> code-writer -> reviewer) followed by a terminal
``write_gate`` node that expresses the human-in-the-loop approval as a LangGraph
``interrupt()`` (ORCH-03). RF-3 boundary decision: **own the StateGraph and use
Deep Agents inside nodes** as the per-role harness, rather than letting
``create_deep_agent`` own the whole graph. That keeps durable-state and human-gate
control in our hands and makes the deterministic stub path trivial.

ORCH-03 / RF-1 load-bearing security decision: the ``write_gate`` node's ``interrupt()``
is the durable PAUSE mechanism ONLY. It does NOT execute the write, and it does NOT read
or trust any approver identity carried in the resumed value. The Phase-1 signed-token +
payload-hash ledger remains the single decision authority; the write executes only in
``runner._resume_after_approval`` under ``approvals.is_approved()``. ``Command(resume=...)``
carries an already-verified boolean decision, never an ``approver_id`` the graph trusts.

Each node follows the optional-dep stub-fallback pattern: when model credentials are
present it would delegate to the bounded roster harness; with creds absent it returns
deterministic, role-distinct output so ``make test`` / ``make smoke`` stay green with no
cloud deps and no model calls (D-01/D-02). Nodes read upstream state and emit
role-distinct fields — never a thin name-and-route pass-through (forbidden by D-02).
"""

from __future__ import annotations

import os
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

# Mutating verbs that mark a write-class action. Kept identical to
# ``orchestrator._run_stub`` so the approval path is exercised the same way on both the
# real-graph and stub-fallback paths.
WRITE_TRIGGERS: tuple[str, ...] = (
    "create",
    "update",
    "send",
    "publish",
    "invoice",
    "commit",
    "delete",
)


class MeshState(TypedDict, total=False):
    """Shared state threaded planner -> researcher -> code_writer -> reviewer.

    ``total=False`` so the initial state may carry only ``prompt``; each node fills in
    its own role-distinct field as the run progresses.
    """

    prompt: str
    plan: str
    research: str
    code: str
    review: str
    proposed_writes: list[dict]
    # Set by ``write_gate_node`` from the resumed ``Command(resume=...)`` value: an
    # already-verified boolean decision, NOT an identity. ``done`` marks the terminal,
    # no-write path (no proposed writes -> no interrupt).
    decision: object
    done: bool


def _model_credentials_present() -> bool:
    """True when a gateway/model credential is available to drive real delegation.

    With no creds, nodes take the deterministic path (no model call). Phase 3 wires the
    LiteLLM-compatible gateway; until then any of these env vars signals "real model
    reachable". Absent here and in CI, so the stub path runs.
    """
    return any(
        os.getenv(var)
        for var in (
            "MODEL_GATEWAY_BASE_URL",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "VERTEX_PROJECT",
        )
    )


def planner_node(state: MeshState) -> MeshState:
    """Decompose the prompt into an ordered plan."""
    prompt = state.get("prompt", "")
    if _model_credentials_present():  # pragma: no cover - needs model creds (Phase 3)
        from agent_mesh.worker.roster import build_roster

        build_roster()  # bounded roster; real delegation wired in Phase 3
    plan = f"[plan] steps to address: {prompt[:80]}"
    return {"plan": plan}


def researcher_node(state: MeshState) -> MeshState:
    """Gather evidence / route tools off the plan (researcher / tool-router)."""
    plan = state.get("plan", "")
    research = f"[research] evidence gathered for: {plan[len('[plan] '):][:80]}"
    return {"research": research}


def code_writer_node(state: MeshState) -> MeshState:
    """Draft code / proposed patches from the plan + research."""
    research = state.get("research", "")
    code = f"[code] draft artifact derived from: {research[len('[research] '):][:80]}"
    return {"code": code}


def reviewer_node(state: MeshState) -> MeshState:
    """Review outputs and surface write-class actions for the approval gate.

    Derives ``proposed_writes`` from the ORIGINAL prompt using the same write-trigger
    heuristic as ``orchestrator._run_stub`` so the approval path is exercised
    identically on the real-graph path. Proposed writes are NEVER executed here.
    """
    prompt = state.get("prompt", "")
    code = state.get("code", "")
    lowered = prompt.lower()
    proposed: list[dict] = []
    if any(trigger in lowered for trigger in WRITE_TRIGGERS):
        proposed.append(
            {
                "tool_name": "hubspot_create_deal",
                "category": "write",
                "parameters": {
                    "deal_name": prompt[:80],
                    "stage": "appointmentscheduled",
                },
            }
        )
    review = (
        f"[review] approved draft ({len(code)} chars); "
        f"{len(proposed)} write-class action(s) require approval"
    )
    return {"review": review, "proposed_writes": proposed}


def write_gate_node(state: MeshState) -> MeshState:
    """Terminal human-in-the-loop gate (ORCH-03).

    If the reviewer surfaced no write-class action, complete immediately ({"done": True}).
    Otherwise pause the graph with a LangGraph ``interrupt()`` carrying the proposed
    writes. ``interrupt()`` checkpoints the run and suspends it; the run resumes from the
    durable checkpoint when ``Command(resume=<verified decision>)`` is dispatched back, at
    which point ``interrupt()`` RETURNS that resumed value and the node records it under
    ``decision``.

    RF-1 security invariants (do NOT relax):

    * This node NEVER executes the write. The Tool Gateway ``.execute`` lives only in
      ``runner._resume_after_approval``, gated by ``approvals.is_approved()``.
    * The resumed value is an already-verified boolean decision ONLY. This node MUST NOT
      read, trust, or persist an ``approver_id`` from it — the approver is derived solely
      from the signed token at ``verify_approval_token`` (SEC-01). ``interrupt()`` is the
      pause mechanism; the signed-token ledger is the decision authority. The interrupt is
      NEVER a second, weaker approval path.
    """
    if not state.get("proposed_writes"):
        return {"done": True}
    # Lazy import: the stub path never reaches a compiled graph, so importing
    # ``interrupt`` here keeps the no-stack fallback free of langgraph.types.
    from langgraph.types import interrupt

    decision = interrupt({"proposed_writes": state["proposed_writes"]})
    # ``decision`` is the verified boolean carried by Command(resume=...). We record it
    # for observability; we do NOT branch on an identity and do NOT execute the write.
    return {"decision": decision}


def build_graph() -> StateGraph:
    """Build the uncompiled supervisor ``StateGraph`` (topology + write-gate).

    Wiring: START -> planner -> researcher -> code_writer -> reviewer -> write_gate -> END.
    ``write_gate`` is the terminal node and expresses the approval pause as an
    ``interrupt()`` (ORCH-03). Returns the *uncompiled* graph so the caller controls
    compilation; ``orchestrator`` compiles it WITH a durable checkpointer (PostgresSaver
    in prod / file-backed SqliteSaver in test) so the interrupt survives a restart.
    """
    graph: StateGraph = StateGraph(MeshState)

    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("code_writer", code_writer_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("write_gate", write_gate_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "researcher")
    graph.add_edge("researcher", "code_writer")
    graph.add_edge("code_writer", "reviewer")
    graph.add_edge("reviewer", "write_gate")
    graph.add_edge("write_gate", END)

    return graph
