"""OBS-02 live lane (D-08): seed a versioned prompt + dataset + an EXAMPLE eval.

These tests run ONLY under ``pytest -m live`` AND only when real Langfuse
credentials are exported (``LANGFUSE_PUBLIC_KEY`` + ``LANGFUSE_SECRET_KEY``). The
default ``make test`` run never reaches a real Langfuse — it deselects ``live`` and
the per-test skip-gate below fires if creds are absent.

Scope (D-08): prove the Langfuse-NATIVE OBS-02 path end-to-end —
  * ≥1 versioned prompt registered (``create_prompt(labels=["production"])``);
  * one dataset seeded (``create_dataset`` + ``create_dataset_item``);
  * one EXAMPLE/TRIVIAL eval registered (``create_score`` on a dataset run).
NOT in scope: a real LLM-judge scoring engine — that is Phase 4 / SI-01. We register
a trivial score to prove the path exists, not to evaluate model quality.
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.live


def _langfuse_client():
    """A real Langfuse client, or skip when creds/SDK are absent.

    The ``live`` marker gates on ``-m live``; this gate additionally requires
    Langfuse-specific creds (the shared ``live_creds`` fixture gates on provider
    creds, which OBS-02 seeding does not use)."""
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        pytest.skip("LANGFUSE_PUBLIC_KEY/SECRET_KEY unset; OBS-02 live seed needs them")
    from langfuse import Langfuse

    return Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    )


def test_seed_versioned_prompt():
    client = _langfuse_client()
    name = "agent-mesh/planner-system"
    client.create_prompt(
        name=name,
        prompt="You are the planner. Decompose the task into an ordered plan.",
        labels=["production"],
        type="text",
    )
    fetched = client.get_prompt(name, label="production")
    assert fetched.prompt


def test_seed_dataset_and_example_eval():
    client = _langfuse_client()
    dataset_name = "phase3-seed"
    client.create_dataset(
        name=dataset_name,
        description="OBS-02 seed dataset (phase 3): example task evidence.",
    )
    client.create_dataset_item(
        dataset_name=dataset_name,
        input={"prompt": "summarise the meeting notes"},
        expected_output={"summary": "a concise summary of the notes"},
    )

    # EXAMPLE/TRIVIAL eval: register a single score to prove the eval path exists.
    # NOT a real LLM-judge harness (Phase 4 / SI-01). A standalone trace id keys the
    # score so the call is self-contained.
    trace_id = uuid.uuid4().hex + uuid.uuid4().hex  # 64-hex, langfuse trace id shape
    client.create_score(
        name="example-eval",
        value=1.0,
        data_type="NUMERIC",
        trace_id=trace_id[:32],
        comment="example trivial eval (OBS-02 path proof, not a real judge)",
    )
    client.flush()
