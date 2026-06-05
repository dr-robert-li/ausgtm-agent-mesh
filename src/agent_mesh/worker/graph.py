"""Real LangGraph ``StateGraph`` topology for the supervisor mesh (ORCH-01).

This module owns the orchestration graph: four declared role nodes
(planner -> researcher/tool-router -> code-writer -> reviewer, reviewer terminal)
wired into a real ``StateGraph``. RF-3 boundary decision: **own the StateGraph and use
Deep Agents inside nodes** as the per-role harness, rather than letting
``create_deep_agent`` own the whole graph. That keeps durable-state and human-gate
control in our hands (02-02) and makes the deterministic stub path trivial.

This plan delivers **topology only**. There is deliberately none of the durable-state
or human-gate machinery here:

* the graph is compiled by the caller with no durable-state saver (the Postgres saver
  arrives in 02-02), and
* there is no write-gate / pause node (also 02-02).

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


def build_graph() -> StateGraph:
    """Build the uncompiled supervisor ``StateGraph`` (topology only).

    Wiring: START -> planner -> researcher -> code_writer -> reviewer -> END. Reviewer
    is terminal. Returns the *uncompiled* graph so the caller controls compilation; in
    this plan ``orchestrator`` compiles it with no durable-state saver (02-02 adds one).
    """
    graph: StateGraph = StateGraph(MeshState)

    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("code_writer", code_writer_node)
    graph.add_node("reviewer", reviewer_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "researcher")
    graph.add_edge("researcher", "code_writer")
    graph.add_edge("code_writer", "reviewer")
    graph.add_edge("reviewer", END)

    return graph
