"""SI-02b: boot-time set-once active-version loader + non-hot promotion proof.

These tests are the criterion-5 chokepoint: a promotion (or rollback) writes a
new active-version pointer to the store, but the *running* process keeps serving
the version it read at boot until an explicit reload. There is no call-time read
of the active version anywhere in the hot path.
"""

import pytest

from agent_mesh.contracts.enums import ApprovalDecision, Entrypoint, ProposalType
from agent_mesh.contracts.models import TaskRecord
from agent_mesh.services import self_improvement as si
from agent_mesh.services import version_pin


@pytest.fixture(autouse=True)
def _reset_active_version():
    """Each test simulates a fresh boot: the module cache is shared global state,
    so reset it before and after to keep tests isolated."""
    version_pin._reset()
    yield
    version_pin._reset()


def _task(repo) -> TaskRecord:
    task = TaskRecord(
        tenant_id="t",
        client_slug="c",
        entrypoint=Entrypoint.API,
        requester={"requester_id": "u1", "entrypoint": "api"},
        session_id="s1",
        prompt="summarize the kickoff notes",
    )
    return repo.create_task(task)


def _promote(repo, *, promoted_version: str, previous_version: str | None):
    """Drive a proposal through the full evaluate -> approve -> promote chain."""
    task = _task(repo)
    proposal = si.reflect_on_task(
        repo,
        task,
        proposal_type=ProposalType.EVAL_CASE,
        title="add regression case",
        rationale="cover the bug",
        proposed_patch="def test_x(): assert True",
    )
    si.evaluate_proposal(repo, proposal.proposal_id)
    si.open_promotion_approval(repo, proposal.proposal_id)
    si.record_approval_decision(
        repo, proposal.proposal_id, ApprovalDecision.APPROVED, "human:1", "slack"
    )
    return si.promote_proposal(
        repo,
        proposal.proposal_id,
        promoted_version=promoted_version,
        previous_version=previous_version,
    )


# --- Task 1: version_pin.py boot-time set-once loader (non-hot) ---------------


def test_active_version_none_before_boot():
    # Before any load_active_version_at_boot() call, the cache is empty.
    assert version_pin.active_version() is None


def test_active_version_set_once_at_boot(repo):
    # Boot with v1 in the store.
    repo.set_active_version("t", "v1", promotion_id=None)
    loaded = version_pin.load_active_version_at_boot(repo, "t")
    assert loaded == "v1"
    assert version_pin.active_version() == "v1"

    # A pointer write to the store does NOT change active_version() mid-run
    # (non-hot, criterion 5): the running process keeps serving v1.
    repo.set_active_version("t", "v2", promotion_id=None)
    assert version_pin.active_version() == "v1"

    # Only an explicit reload (a fresh boot step) picks up the new pointer.
    reloaded = version_pin.load_active_version_at_boot(repo, "t")
    assert reloaded == "v2"
    assert version_pin.active_version() == "v2"


# --- Task 2: promote/rollback wiring (non-hot proof + rollback re-point) ------


def test_promotion_is_non_hot(repo):
    # Boot with v1 active.
    repo.set_active_version("t", "v1", promotion_id=None)
    version_pin.load_active_version_at_boot(repo, "t")
    assert version_pin.active_version() == "v1"

    # Promote to v2: an ML-BOM is generated and the active pointer is written,
    # but the loaded active_version() is UNCHANGED until an explicit reload.
    promotion = _promote(repo, promoted_version="v2", previous_version="v1")
    assert promotion.ai_bom_snapshot_id is not None  # ML-BOM linked (SI-02)
    assert version_pin.active_version() == "v1"  # non-hot: still v1

    # The store pointer was written non-hot; a reload reflects v2.
    assert repo.current_active_version("t") == "v2"
    version_pin.load_active_version_at_boot(repo, "t")
    assert version_pin.active_version() == "v2"


def test_rollback_repoints_to_previous_version(repo):
    repo.set_active_version("t", "v1", promotion_id=None)
    version_pin.load_active_version_at_boot(repo, "t")

    promotion = _promote(repo, promoted_version="v2", previous_version="v1")
    # After promote, the store points at v2 (non-hot until reload).
    assert repo.current_active_version("t") == "v2"

    # Rollback re-points the active pointer to previous_version (D-13: not a
    # mere status flip). The next boot reads the restored version.
    si.rollback_promotion(repo, promotion.promotion_id, reason="regression")
    assert repo.current_active_version("t") == "v1"
    version_pin.load_active_version_at_boot(repo, "t")
    assert version_pin.active_version() == "v1"
