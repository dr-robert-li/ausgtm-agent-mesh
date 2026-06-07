"""Default-lane (creds-free) tests for the held-out evaluation harness (06-02).

The harness wraps Langfuse ``run_experiment`` over a versioned held-out set of
deterministic frozen-context snapshots and feeds a pure-Python no-regression gate.
All of it must run with NO Langfuse keys set (``make test`` stays creds-free).
"""

from __future__ import annotations

from agent_mesh.services import eval_harness as eh


def test_frozen_items_deterministic(frozen_holdout_items):
    """SI-01c: the same snapshot input always yields the same frozen item dict."""
    first = eh.build_frozen_items(frozen_holdout_items)
    second = eh.build_frozen_items(frozen_holdout_items)
    assert first == second
    # Each item carries a stable item_id in metadata.
    ids = [it["metadata"]["item_id"] for it in first]
    assert ids == sorted(ids) or len(set(ids)) == len(ids)  # stable + unique
    assert all(it["input"] is not None for it in first)


def test_held_out_pool_identity_is_stable_and_importable():
    """SI-01a: held_out_item_ids() is a deterministic, non-empty, importable set."""
    ids_a = eh.held_out_item_ids()
    ids_b = eh.held_out_item_ids()
    assert ids_a == ids_b
    assert isinstance(ids_a, set)
    assert len(ids_a) > 0
    # The pool itself maps 1:1 to those ids.
    pool = eh.held_out_pool()
    pool_ids = {it["metadata"]["item_id"] for it in pool}
    assert pool_ids == ids_a


def test_run_candidate_creds_free(monkeypatch, frozen_holdout_items):
    """The runner executes locally with NO Langfuse keys set and returns per-item scores."""
    for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(var, raising=False)
    items = eh.build_frozen_items(frozen_holdout_items)
    result = eh.run_candidate(items, eh.replay_task, evaluators=[eh.exact_match])
    scores = eh.scores_by_item(result)
    # One score per item, keyed by the stable item_id.
    assert set(scores) == {it["metadata"]["item_id"] for it in items}
    # The deterministic replay task returns expected_output -> exact_match == 1.0.
    assert all(v == 1.0 for v in scores.values())
