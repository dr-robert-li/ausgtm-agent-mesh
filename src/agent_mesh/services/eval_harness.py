"""Held-out evaluation harness (SI-01 / SI-01a / SI-01b / SI-01c).

This module is the REAL scoring engine that replaces the boolean
``self_improvement.evaluate_proposal`` stub. It has two halves, deliberately
separated so the promotion-eligibility decision stays reproducible and creds-free:

* **A Langfuse ``run_experiment`` runner** over a versioned held-out set of
  *deterministic frozen-context snapshots*. Mirrors ``observability.py``'s
  lazy-optional-dep + creds-free-degrade pattern: Langfuse is imported lazily and
  a key-less ``Langfuse()`` is "disabled" (no upload) yet ``run_experiment`` STILL
  executes locally over the supplied data (verified in 06-RESEARCH). The default-
  lane task is a deterministic offline replay — no model call, no network.
* **A pure-Python no-regression gate** (``passes_no_regression``) that compares a
  candidate's per-item scores against a stored golden baseline at BOTH the
  aggregate AND the item level. Aggregate alone hides per-item regressions (D-03),
  so the gate requires candidate-mean >= baseline-mean AND no single item dropping
  beyond a configured threshold. This gate is the actual promotion-eligibility
  check; it is kept OUT of ``run_experiment`` so it stays creds-free + reproducible.

Held-out pool identity (SI-01a): ``held_out_pool()`` / ``held_out_item_ids()`` are
a DISTINCT importable surface — the held-out set the gate scores against. The
06-03 proposer must mine only durable traces and never read this pool; the
zero-overlap test lives in 06-03 (T-06-03b).

Anti-patterns avoided (06-RESEARCH / 06-PATTERNS): no live-creds gate import (the
default lane must stay green); ``run_experiment`` is never used AS the gate; dataset
versions use the public ``get_dataset(name, version=)`` path, never the private
version kwarg.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from statistics import mean
from typing import Any

# --- Config-driven defaults (module constants, not call-site literals) ------
# The held-out pool VERSION pins which frozen set + golden baseline the gate uses.
HELD_OUT_VERSION = "2026-06-07"
# Per-item regression tolerance: a single item may not drop more than this below
# its baseline score, even when the aggregate holds (D-03 masking guard).
DEFAULT_ITEM_THRESHOLD = 0.05
# The committed golden baseline (creds-free, version-keyed JSON under git history).
_BASELINE_PATH = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "holdout_baseline.json"
)
# The versioned held-out snapshots. Deterministic, in-repo, distinct from any
# optimization signal the proposer (06-03) consumes. Each is a context snapshot;
# build_frozen_items() freezes it into a LocalExperimentItem-shaped dict.
_HELD_OUT_SNAPSHOTS: tuple[dict[str, Any], ...] = (
    {
        "item_id": "holdout-001",
        "input": "Summarize the Q1 revenue report.",
        "expected_output": "Q1 revenue grew 12% QoQ.",
        "category": "summary",
    },
    {
        "item_id": "holdout-002",
        "input": "Classify sentiment: 'This release is fantastic.'",
        "expected_output": "positive",
        "category": "classification",
    },
    {
        "item_id": "holdout-003",
        "input": "Extract the due date from: 'Invoice due 2026-07-01.'",
        "expected_output": "2026-07-01",
        "category": "extraction",
    },
)


def build_frozen_items(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Freeze context snapshots into deterministic LocalExperimentItem dicts (SI-01c).

    The same snapshot always yields the same item dict: a stable ``item_id`` is
    derived from the snapshot's own ``item_id`` (or a deterministic fallback keyed
    by position+input), and the input/expected_output are copied verbatim. No
    timestamps, no randomness — two builds over the same input are ``==``.
    """
    items: list[dict[str, Any]] = []
    for idx, snap in enumerate(snapshots):
        # Prefer an explicit item_id; fall back to a deterministic positional id.
        item_id = snap.get("item_id")
        if item_id is None:
            meta = snap.get("metadata") or {}
            item_id = meta.get("item_id") or f"item-{idx:03d}"
        metadata = {"item_id": item_id}
        category = snap.get("category") or (snap.get("metadata") or {}).get("category")
        if category is not None:
            metadata["category"] = category
        items.append(
            {
                "input": snap["input"],
                "expected_output": snap.get("expected_output"),
                "metadata": metadata,
            }
        )
    return items


def held_out_pool() -> list[dict[str, Any]]:
    """Return the versioned held-out set as frozen LocalExperimentItem dicts.

    This is the held-out POOL IDENTITY (SI-01a): a distinct importable surface the
    no-regression gate scores against. The proposer (06-03) must never read it.
    """
    return build_frozen_items(list(_HELD_OUT_SNAPSHOTS))


def held_out_item_ids() -> set[str]:
    """Return the stable set of held-out item_ids (the pool identity, SI-01a).

    Importable from other modules; 06-03's zero-overlap test asserts the proposer's
    training signal never intersects this set.
    """
    return {it["metadata"]["item_id"] for it in held_out_pool()}


def replay_task(*, item: dict[str, Any], **_: Any) -> Any:
    """Deterministic offline replay task for the default (creds-free) lane.

    Returns the item's ``expected_output`` verbatim — no model call. This makes the
    default-lane candidate score identical to the golden baseline by construction;
    real candidate-vs-baseline discrimination is the live LLM judge in 06-04.
    """
    return item.get("expected_output")


def exact_match(*, input: Any, output: Any, expected_output: Any, metadata: Any, **_: Any):
    """Default deterministic evaluator: 1.0 on exact match, else 0.0.

    Returns a langfuse ``Evaluation``. Imported lazily so this module stays
    importable without langfuse installed (mirrors observability.py).
    """
    from langfuse.experiment import Evaluation

    return Evaluation(name="exact_match", value=float(output == expected_output))


def run_candidate(
    items: list[dict[str, Any]],
    task_fn: Callable[..., Any],
    *,
    evaluators: list[Callable[..., Any]],
    name: str = "si-candidate",
):
    """Run ``task_fn`` over ``items`` via Langfuse ``run_experiment``, creds-free.

    Builds a key-less ``Langfuse()`` (disabled: no upload) and still executes the
    experiment locally over the supplied frozen items. Returns the
    ``ExperimentResult`` (its ``.item_results`` carry per-item scores). Langfuse is
    imported lazily so a default-lane import of this module never crashes when the
    optional dep is absent.
    """
    from langfuse import Langfuse

    client = Langfuse()  # no keys -> disabled (no upload), run_experiment still runs
    return client.run_experiment(name=name, data=items, task=task_fn, evaluators=evaluators)


def scores_by_item(result: Any, *, evaluator: str = "exact_match") -> dict[str, float]:
    """Extract a ``{item_id: score}`` map from an ``ExperimentResult``.

    Reads each per-item result's ``evaluations`` list, picking the named
    evaluator's scalar ``value``. The item_id comes from the frozen item's
    ``metadata.item_id`` so the gate can align candidate and baseline per item.
    """
    scores: dict[str, float] = {}
    for item_result in result.item_results:
        item = getattr(item_result, "item", {}) or {}
        item_id = (item.get("metadata") or {}).get("item_id")
        if item_id is None:
            # Raise rather than skip (WR-06): a silently-dropped item becomes a
            # missing candidate key in passes_no_regression, which treats it as a
            # 0.0 score — manufacturing a phantom regression of up to 1.0 against an
            # item that was never scored, with no diagnostic. Fail loudly instead.
            raise ValueError(
                f"eval item missing metadata.item_id; cannot score: {item!r}"
            )
        value = None
        for ev in getattr(item_result, "evaluations", []) or []:
            if getattr(ev, "name", None) == evaluator:
                value = ev.value
                break
        if value is not None:
            scores[item_id] = float(value)
    return scores


def load_baseline(*, version: str = HELD_OUT_VERSION) -> dict[str, float]:
    """Load the committed golden baseline scores for ``version`` (creds-free).

    The baseline is a version-keyed JSON fixture under git history (T-06-06: a
    committed, code-reviewed baseline is accepted for the POC; production would
    sign it). Chosen over durable storage to keep 06-02 off repository.py / the
    0004 migration (06-RESEARCH Open-Q2). Returns ``{item_id: score}``.
    """
    data = json.loads(_BASELINE_PATH.read_text())
    scores = data[version]
    return {item_id: float(score) for item_id, score in scores.items()}


def passes_no_regression(
    candidate: dict[str, float],
    baseline: dict[str, float],
    *,
    item_threshold: float = DEFAULT_ITEM_THRESHOLD,
) -> tuple[bool, list[dict[str, Any]]]:
    """Promotion-eligibility gate: aggregate AND item-level no-regression (SI-01b).

    Two-stage by design (D-03): the aggregate mean check alone hides per-item
    regressions, so a candidate that games the average must still clear every item.

    * Candidate mean < baseline mean -> ``(False, [{"reason": "aggregate_below_baseline"}])``.
    * Any item where ``baseline - candidate > item_threshold`` -> ``(False, [regressions])``.
    * Otherwise ``(True, [])``.

    Pure stdlib so it is reproducible and creds-free (never inside run_experiment).
    Items present in the baseline but missing from the candidate are treated as a
    regression to 0.0 (a dropped item is the worst possible regression).
    """
    if not baseline:
        return True, []

    candidate_mean = mean(candidate.values()) if candidate else 0.0
    baseline_mean = mean(baseline.values())
    if candidate_mean < baseline_mean:
        return False, [
            {
                "reason": "aggregate_below_baseline",
                "candidate_mean": candidate_mean,
                "baseline_mean": baseline_mean,
            }
        ]

    regressions: list[dict[str, Any]] = []
    for item_id, baseline_score in baseline.items():
        candidate_score = candidate.get(item_id, 0.0)
        delta = baseline_score - candidate_score
        if delta > item_threshold:
            regressions.append(
                {
                    "item_id": item_id,
                    "baseline_score": baseline_score,
                    "candidate_score": candidate_score,
                    "delta": delta,
                }
            )
    return (not regressions), regressions
