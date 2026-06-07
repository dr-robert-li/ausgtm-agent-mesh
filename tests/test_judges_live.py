"""Live-lane tests for the SI-01d LLM-judge (order-swap, calibration, Type-I gate).

These tests run ONLY under ``pytest -m live`` (``make test-live``) AND only when
real provider/gateway credentials are exported — they consume the shared
``live_creds`` fixture (``conftest.py:114-126``), exactly like
``tests/test_langfuse_seed_live.py``. The default ``make test`` run
(``pytest -m "not live"``) deselects this whole module: it collects ZERO running
tests here and imports no judge code at runtime, keeping the default lane creds-free
(SI-01d / SI criterion 6 / threat T-06-12).

The judge LOGIC (order-swap agreement, TPR/FPR calibration, exact-binomial Type-I
gate, close-margin non-sole-arbiter guard) is deterministic pure-Python, so we drive
it with an injected deterministic ``compare`` rather than a real model — the tests
prove the guards' behaviour without spending tokens, while still living entirely in
the credential-gated ``live`` lane (the live gate is the lane contract, not a per-call
network requirement)."""

from __future__ import annotations

import pytest

from agent_mesh.eval import judges as j

pytestmark = pytest.mark.live


def _agreeing_compare(winner: str):
    """A deterministic pairwise judge that always prefers ``winner`` REGARDLESS of
    position — so both orderings agree (no position bias)."""

    def _compare(first, second):
        # winner is one of the two objects; return its positional label.
        if first is winner:
            return "first"
        if second is winner:
            return "second"
        return "tie"

    return _compare


def _position_biased_compare():
    """A deterministic judge that ALWAYS prefers whatever it is shown first — pure
    position bias. Order-swap must neutralise this into a non-win."""

    def _compare(first, second):  # noqa: ARG001
        return "first"

    return _compare


def test_order_swap_counts_win_only_when_both_orderings_agree(live_creds):
    cand, base = object(), object()
    # An unbiased judge that always prefers the candidate in both orderings -> win.
    agree = j.order_swap_verdict(
        candidate=cand, baseline=base, compare=_agreeing_compare(cand)
    )
    assert agree.candidate_wins is True
    assert agree.is_position_bias_flip is False

    # A purely position-biased judge (always picks first) flips between orderings ->
    # NOT a win, flagged as a position-bias flip (D-05).
    biased = j.order_swap_verdict(
        candidate=cand, baseline=base, compare=_position_biased_compare()
    )
    assert biased.candidate_wins is False
    assert biased.is_position_bias_flip is True


def test_calibration_returns_tpr_fpr_bounded_in_unit_interval(live_creds):
    # Labelled fixture: judge agrees with human on 4/5, one false-positive.
    judge_labels = [True, True, False, False, True]
    human_labels = [True, True, False, True, False]
    cfg = j.JudgeConfig(min_calibration_n=1, min_tpr=0.0, max_fpr=1.0)
    cal = j.calibrate(judge_labels, human_labels, config=cfg)
    assert 0.0 <= cal["tpr"] <= 1.0
    assert 0.0 <= cal["fpr"] <= 1.0
    assert cal["n"] == 5
    # tp=2, fn=1 -> tpr=2/3 ; fp=1, tn=1 -> fpr=1/2.
    assert cal["tpr"] == pytest.approx(2 / 3)
    assert cal["fpr"] == pytest.approx(1 / 2)
    assert cal["trusted"] is True  # within the relaxed cfg gates

    # Misaligned lengths are a contract error.
    with pytest.raises(ValueError):
        j.calibrate([True], [True, False], config=cfg)


def test_finite_sample_type_i_gate_rejects_below_configured_alpha(live_creds):
    cfg = j.JudgeConfig(alpha=0.05, null_win_rate=0.5)
    # 10/10 order-swap-agreeing wins: exact tail 0.5^10 ~= 0.000977 <= alpha -> PASS.
    assert j.binomial_upper_tail(10, 10, 0.5) == pytest.approx(0.5**10)
    assert j.passes_type_i(10, 10, config=cfg) is True
    # 6/10 wins: tail ~= 0.377 > alpha -> the gate REJECTS (no false GO).
    assert j.passes_type_i(6, 10, config=cfg) is False
    # Zero-sample can never reject H0.
    assert j.passes_type_i(0, 0, config=cfg) is False
    # Tightening alpha makes a marginal sample fail (config-driven, not hardcoded).
    strict = j.JudgeConfig(alpha=0.0005, null_win_rate=0.5)
    assert j.passes_type_i(10, 10, config=strict) is False


def test_close_margin_guard_defers_to_deterministic_gate(live_creds):
    cfg = j.JudgeConfig(close_margin=0.05)
    cand = object()
    # 10/10 agreeing wins -> the judge itself says GO ...
    verdicts = [j.PairwiseVerdict("candidate", "candidate")] * 10
    close = j.judge_decision(
        candidate_score=0.50, baseline_score=0.51, verdicts=verdicts, config=cfg
    )
    assert close.close_margin is True
    # ... but at a close margin it is NOT the sole arbiter — caller defers to the
    # deterministic harness gate (D-05). judge_go may be True yet sole_arbiter False.
    assert close.sole_arbiter is False

    far = j.judge_decision(
        candidate_score=0.90, baseline_score=0.50, verdicts=verdicts, config=cfg
    )
    assert far.close_margin is False
    assert far.sole_arbiter is True
    assert far.judge_go is True
    del cand


def test_run_evaluator_plugs_into_harness_with_injected_compare(live_creds):
    # The run-level evaluator (the 06-02 run_evaluators slot) builds with an injected
    # deterministic compare so no real model / network is needed in the test, while
    # still proving the live-lane plug-in shape.
    cand = "candidate-output"
    baseline_by_item = {"holdout-001": "baseline-output"}
    evaluator = j.make_run_evaluator(
        baseline_by_item=baseline_by_item,
        compare=_agreeing_compare(cand),
    )
    result = evaluator(
        input="prompt",
        output=cand,
        expected_output="baseline-output",
        metadata={"item_id": "holdout-001"},
    )
    assert result.name == "llm_judge_order_swap"
    assert result.value == 1.0
