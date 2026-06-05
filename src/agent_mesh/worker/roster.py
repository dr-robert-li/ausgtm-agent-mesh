"""Declared, bounded Deep Agents roster for the supervisor mesh.

ORCH-01 / CLAUDE.md §1-§3 guardrail: the subagent team is a *declared, bounded,
supervisor-orchestrated* roster — planner, researcher/tool-router, code-writer,
reviewer — and **never** an uncontrolled self-spawning swarm. Exactly four members.

Deep Agents (`create_deep_agent`) auto-injects a fifth ``general-purpose`` subagent
"unless disabled or replaced" (verified empirically against deepagents 0.6.8). That
would make the effective roster five and violate the bound, so :func:`build_roster`
disables it via a harness profile and asserts the effective declared roster is exactly
four before returning. The size is logged at build time (ORCH-01: "log roster size at
startup").

This module is import-safe with no agents stack installed: the heavy ``deepagents``
imports are deferred into :func:`build_roster`, which only runs when
``deep_agents_available()`` is True. ``ROSTER`` and :func:`roster_size` are pure data
and need no optional deps, so the bound is assertable everywhere (including ``make
test`` on macOS with no cloud deps).

Tracing guardrail (CLAUDE.md): the optional LangChain tracing SDK is never imported
and its enabling env vars are never set; observability flows through Langfuse only.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# The general-purpose subagent name Deep Agents auto-injects. We disable it so the
# effective roster stays bounded at the four declared members (T-02-01-E mitigation).
GENERAL_PURPOSE_NAME = "general-purpose"

# Declared, bounded roster. Each entry is a Deep Agents ``SubAgent`` spec
# (name/description/system_prompt). ``model`` is intentionally omitted — Phase 3 swaps
# a gateway-routed model in via ``create_deep_agent(model=...)``; subagents inherit it.
ROSTER: list[dict[str, str]] = [
    {
        "name": "planner",
        "description": "Decompose the task into an ordered, verifiable plan of steps.",
        "system_prompt": (
            "You are the planner. Read the task and produce a short, ordered plan of "
            "concrete steps. Do not execute tools; only plan. Hand the plan to the "
            "researcher."
        ),
    },
    {
        "name": "researcher",
        "description": "Gather evidence and route tool calls (researcher / tool-router).",
        "system_prompt": (
            "You are the researcher / tool-router. Given the plan, gather the evidence "
            "and identify which tools are needed for each step. Never execute write-class "
            "tools; surface them as proposals for the reviewer to gate."
        ),
    },
    {
        "name": "code_writer",
        "description": "Draft code, artifacts, and proposed patches from the research.",
        "system_prompt": (
            "You are the code-writer. Using the plan and research, draft the code, "
            "artifacts, or proposed patches required. Produce proposals only; nothing is "
            "applied until the reviewer and the human approval gate clear it."
        ),
    },
    {
        "name": "reviewer",
        "description": "Review outputs and surface write-class actions for approval.",
        "system_prompt": (
            "You are the reviewer. Inspect the plan, research, and drafted code. Surface "
            "every write-class action (create/update/send/publish/invoice/commit/delete) "
            "as a proposed write that the human approval gate must clear before execution."
        ),
    },
]


def roster_size() -> int:
    """Number of declared roster members. Bounded at exactly four (ORCH-01)."""
    return len(ROSTER)


def _disable_general_purpose(model: str) -> None:
    """Register a harness profile that disables the auto general-purpose subagent.

    Deep Agents 0.6.8 adds ``general-purpose`` inside ``create_deep_agent`` unless the
    model's harness profile sets ``general_purpose_subagent.enabled = False`` (or an
    explicit subagent named ``general-purpose`` is supplied). Registering the profile
    for this model id is the documented, model-scoped disable — it does not mutate
    global behavior for other models. Idempotent: re-registering the same profile is a
    no-op for our purposes.
    """
    from deepagents import (  # noqa: PLC0415 - deferred optional import
        GeneralPurposeSubagentProfile,
        HarnessProfile,
        register_harness_profile,
    )

    register_harness_profile(
        model,
        HarnessProfile(
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)
        ),
    )


def effective_roster_names(model: str = "anthropic:claude-sonnet-4-5") -> frozenset[str]:
    """The effective declared subagent names, observed creds-free.

    Builds a ``SubAgentMiddleware`` over our :data:`ROSTER` and reads its public
    ``subagent_names`` accessor. ``SubAgentMiddleware`` does NOT auto-add the
    general-purpose subagent (that injection lives in the ``create_deep_agent``
    factory), so this is the authoritative, model-creds-free view of the *declared*
    roster and lets us prove ``general-purpose`` is absent (T-02-01-E).

    Requires the agents stack; call only when ``deep_agents_available()`` is True.
    """
    from deepagents.backends import StateBackend  # noqa: PLC0415
    from deepagents.middleware.subagents import SubAgentMiddleware  # noqa: PLC0415

    specs = [{**member, "model": model, "tools": []} for member in ROSTER]
    middleware = SubAgentMiddleware(backend=StateBackend(), subagents=specs)
    return frozenset(middleware.subagent_names)


def build_roster(model: str = "anthropic:claude-sonnet-4-5") -> Any:
    """Build the bounded Deep Agents supervisor over the declared four-member roster.

    Disables the auto general-purpose subagent, asserts the effective declared roster
    is exactly four (no ``general-purpose``), logs the size, and returns the compiled
    Deep Agents supervisor. Phase 3 supplies a gateway-routed model; for now the model
    id only selects the harness profile (no network call at build time).

    Raises:
        RuntimeError: if the effective declared roster is not exactly the four declared
            members — the bounded-roster invariant must hold before any run.
    """
    from deepagents import create_deep_agent  # noqa: PLC0415 - deferred optional import

    _disable_general_purpose(model)

    declared = effective_roster_names(model)
    expected = frozenset(member["name"] for member in ROSTER)
    if declared != expected or GENERAL_PURPOSE_NAME in declared:
        raise RuntimeError(
            "bounded-roster invariant violated: effective roster "
            f"{sorted(declared)} != declared {sorted(expected)} "
            "(general-purpose must be disabled; no self-spawning)"
        )

    logger.info("roster size %d: %s", roster_size(), sorted(expected))

    return create_deep_agent(model=model, subagents=[dict(member) for member in ROSTER])
