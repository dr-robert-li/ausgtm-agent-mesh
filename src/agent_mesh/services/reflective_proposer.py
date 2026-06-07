"""GEPA-style offline reflective proposer (SI-03 / SI-01a).

This module is a **separated offline meta-agent**. It mines durable, tenant-scoped
execution traces (Postgres ``tool_calls`` + the task record — NOT live Langfuse
spans), reflects on them to diagnose failures, and emits an **inert**
``SelfImprovementProposal`` (status=DRAFT) through the EXISTING
``self_improvement.reflect_on_task`` seam. It runs a bounded loop that caps
optimization iterations and re-validates each round on the held-out set.

Hard safety boundaries (Option C, CLAUDE.md §8):

* **Inertness (D-08).** Proposals are created via ``reflect_on_task`` only, which
  sets ``status=DRAFT`` and binds ``patch_hash`` at creation. This module NEVER
  imports or calls the promotion/approval path, so nothing it does can mutate
  active instructions, permissions, or routing. Inertness is INHERITED from the
  seam, not re-implemented.
* **Held-out isolation (SI-01a / D-02).** The proposer mines only its own train/dev
  pool and NEVER reads the held-out evaluation set. It does not import the held-out
  pool surface; re-validation reaches the held-out set ONLY through the injected
  gate (the 06-02 ``evaluate_proposal`` path), never as a reflection signal.
  Optimizing against the held-out set is reward hacking that worsens with iterations.
* **Tenant-scoping (DUR-02).** Trace mining is tenant-scoped:
  ``repo.list_tool_calls(task_id, tenant_id)`` only returns the proposing tenant's
  traces.
* **Bounded roster (D-07).** This is a separated offline module. It is NOT a new
  live LangGraph supervisor agent and is NOT wired into ``worker/orchestrator.py``.

The reflection function (``reflect_fn``) is INJECTED: the live lane passes a real
LLM-backed reflector; the default (creds-free) test lane passes the recording
``stub_reflector``. Both are called by keyword (``reflect_fn(evidence=...)``).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from agent_mesh.contracts.enums import ProposalType
from agent_mesh.contracts.models import (
    SelfImprovementProposal,
    TaskRecord,
    ToolCall,
)
from agent_mesh.services import self_improvement
from agent_mesh.services.repository import Repository

# --- Config-driven defaults (config helpers, not call-site literals) --------
# Conservative iteration cap for the bounded improvement loop (RESEARCH Q1/D-15:
# config-driven conservative default, e.g. 3-5). The loop bound is NEVER a bare
# integer literal at the call site (T-06-10).


def _parse_max_iterations() -> int:
    """Resolve SI_IMPROVE_MAX_ITERATIONS lazily, with a clear error (WR-05).

    Parsing at IMPORT time (the old ``int(os.getenv(...))`` module constant) means a
    non-integer env var raises a ``ValueError`` from import machinery, crashing the
    worker before any useful diagnostics. Resolving on first use surfaces a precise,
    actionable message instead.
    """
    raw = os.getenv("SI_IMPROVE_MAX_ITERATIONS", "3")
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(
            f"SI_IMPROVE_MAX_ITERATIONS must be an integer; got {raw!r}"
        ) from None
    if value < 1:
        raise ValueError(f"SI_IMPROVE_MAX_ITERATIONS must be >= 1; got {value}")
    return value


def __getattr__(name: str) -> int:
    """Lazily resolve ``DEFAULT_MAX_ITERATIONS`` on attribute access (PEP 562).

    Keeps ``reflective_proposer.DEFAULT_MAX_ITERATIONS`` working for callers/tests
    while deferring the env parse out of import time so a bad env var never crashes
    module import (WR-05)."""
    if name == "DEFAULT_MAX_ITERATIONS":
        return _parse_max_iterations()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# The proposer's train/dev item-id surface. DELIBERATELY in a distinct namespace
# from the eval harness held-out ids (``holdout-0xx``) so the disjointness proven
# by ``test_holdout_isolation`` (SI-01a) is substantive, not an accident. The
# proposer mines durable traces for these and NEVER reads the held-out pool.
_TRAIN_ITEM_IDS = frozenset({"train-001", "train-002", "train-003"})

# The default reflection-derived proposal kind. PROMPT_PATCH is a sensitive type,
# so ``reflect_on_task`` floors it to HIGH risk (never auto-promotable) — which is
# correct for an autonomously-mined prompt-improvement proposal.
_DEFAULT_PROPOSAL_TYPE = ProposalType.PROMPT_PATCH


class HeldOutLeakError(RuntimeError):
    """Raised when the proposer's train/dev item-ids intersect the held-out set.

    A non-empty intersection means the held-out evaluation signal has leaked into
    the proposer's optimization signal (reward hacking, D-02 / SI-01a)."""


def train_item_ids() -> set[str]:
    """Return the proposer's train/dev item-id surface (the optimization signal).

    This is the COMPLEMENT of the eval harness held-out pool: the proposer mines
    these and the held-out set is protected from its visibility. The zero-overlap
    test asserts ``not (train_item_ids() & eval_harness.held_out_item_ids())``."""
    return set(_TRAIN_ITEM_IDS)


def assert_holdout_isolation(train_ids: set[str], holdout_ids: set[str]) -> None:
    """Raise ``HeldOutLeakError`` if the train/dev and held-out id sets intersect.

    The guard the proposer is constrained by (SI-01a): the held-out pool must never
    be part of the proposer's optimization signal."""
    overlap = train_ids & holdout_ids
    if overlap:
        raise HeldOutLeakError(
            f"held-out set leaked into proposer optimization signal: {sorted(overlap)}"
        )


def propose_from_traces(
    repo: Repository,
    task: TaskRecord,
    reflect_fn: Callable[..., str],
) -> SelfImprovementProposal:
    """Mine durable tenant-scoped traces and emit ONE inert DRAFT proposal.

    1. Reads ``repo.list_tool_calls(task.task_id, task.tenant_id)`` — the durable,
       TENANT-SCOPED trace source (DUR-02). A trace for another tenant is never
       mined here.
    2. Calls ``reflect_fn(evidence=...)`` (BY KEYWORD) to obtain a candidate diff.
       The live lane injects a real LLM-backed reflector; the default test lane
       injects the creds-free ``stub_reflector``.
    3. Emits the diff THROUGH ``self_improvement.reflect_on_task`` so the result is
       DRAFT, patch-hash-bound, and inert. This module never calls promote/approve.
    """
    # Tenant-scoped durable trace mining (DUR-02).
    evidence: Sequence[ToolCall] = repo.list_tool_calls(task.task_id, task.tenant_id)

    # Reflect to obtain a candidate diff. Called by keyword to match the injected
    # reflector's keyword-only ``reflect(*, evidence=...)`` contract.
    diff = reflect_fn(evidence=evidence)

    rationale = (
        f"GEPA-style offline reflection over {len(evidence)} durable tenant-scoped "
        "trace(s); inert DRAFT proposal pending evaluation + human approval."
    )
    evidence_pointers = [c.tool_call_id for c in evidence]

    # Emit through the existing inert seam: status=DRAFT, patch_hash bound at
    # creation, NO promotion. Inertness is inherited, not re-implemented (D-08).
    return self_improvement.reflect_on_task(
        repo,
        task,
        proposal_type=_DEFAULT_PROPOSAL_TYPE,
        title="reflective prompt improvement",
        rationale=rationale,
        proposed_patch=diff,
        agent_id="reflective-proposer",
        evidence_pointers=evidence_pointers,
    )


def _default_gate(repo: Repository, proposal: SelfImprovementProposal) -> bool:
    """Default re-validation gate: the 06-02 held-out evaluation path.

    Delegates to ``self_improvement.evaluate_proposal`` which scores the candidate
    over the held-out pool and applies the pure-Python no-regression gate. The
    proposer reaches the held-out set ONLY through this gate — it never reads the
    held-out pool directly (SI-01a)."""
    result = self_improvement.evaluate_proposal(repo, proposal.proposal_id)
    return bool(result.passed and not result.pending)


@dataclass(frozen=True)
class ImproveLoopResult:
    """Outcome of a bounded improvement loop run."""

    proposal: SelfImprovementProposal
    iterations: int
    passed: bool


def improve_loop(
    repo: Repository,
    task: TaskRecord,
    reflect_fn: Callable[..., str],
    *,
    gate_fn: Callable[[SelfImprovementProposal], bool] | None = None,
    max_iterations: int | None = None,
) -> ImproveLoopResult:
    """Run a BOUNDED reflective-improvement loop (SI-03).

    Each round: mine traces → reflect → emit an inert DRAFT proposal → re-validate
    the candidate on the held-out set via ``gate_fn``. The loop stops EARLY once the
    gate passes; otherwise it halts at exactly ``max_iterations`` (never unbounded —
    T-06-10). ``max_iterations`` defaults to the config-driven, lazily-resolved
    ``_parse_max_iterations()`` (``SI_IMPROVE_MAX_ITERATIONS``; no bare literal at the
    call site, and a bad env var never crashes module import).

    ``gate_fn`` is injectable: the default is the 06-02 held-out gate
    (``_default_gate``); a test injects an always-fail gate to prove boundedness.
    The held-out set is reached ONLY through the gate — never fed back into the
    reflection signal."""
    if gate_fn is None:
        gate_fn = lambda proposal: _default_gate(repo, proposal)  # noqa: E731
    # Resolve the config-driven cap lazily so a bad env var never crashes import
    # (WR-05); an explicit caller value still wins.
    if max_iterations is None:
        max_iterations = _parse_max_iterations()

    last: SelfImprovementProposal | None = None
    iterations = 0
    passed = False
    for _ in range(max_iterations):
        iterations += 1
        last = propose_from_traces(repo, task, reflect_fn)
        if gate_fn(last):
            passed = True
            break

    # Explicit guard, not assert (WR-04): python -O strips assert, and production
    # workers often run with PYTHONOPTIMIZE=1. A zero/empty loop would otherwise
    # fall through to use an unbound `last`. Raise a clear error instead.
    if last is None:
        raise RuntimeError(
            "improve_loop exited without producing a proposal; "
            "max_iterations may be zero or the train set is empty"
        )
    return ImproveLoopResult(proposal=last, iterations=iterations, passed=passed)
