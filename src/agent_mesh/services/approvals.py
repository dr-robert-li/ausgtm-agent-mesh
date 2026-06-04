"""Approval gating for write actions.

Every write-category tool call and every applied prompt-to-code patch must pass
through here. The payload hash binds an approval to the *exact* action proposed,
so an approval cannot be replayed against a mutated payload.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from agent_mesh.contracts.enums import WRITE_CATEGORIES, ApprovalDecision, ToolCategory
from agent_mesh.contracts.models import (
    ApprovalRecord,
    ApprovalRequest,
    ToolCall,
)
from agent_mesh.services.repository import Repository


def requires_approval(category: ToolCategory | str) -> bool:
    """Write-class tools always require approval; reads never do."""
    cat = category if isinstance(category, ToolCategory) else ToolCategory(category)
    return cat in WRITE_CATEGORIES


def payload_hash(payload: dict) -> str:
    """Stable hash of the action payload. Canonical JSON so re-serialization of
    the same logical payload yields the same hash."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_approval_request(
    call: ToolCall, summary: str, evidence: list[str] | None = None
) -> ApprovalRequest:
    return ApprovalRequest(
        task_id=call.task_id,
        tenant_id=call.tenant_id,
        tool_call_id=call.tool_call_id,
        requester_id=call.requester_id,
        summary=summary,
        payload_hash=payload_hash(call.parameters),
        evidence_pointers=evidence or [],
    )


def open_approval(repo: Repository, request: ApprovalRequest) -> ApprovalRecord:
    """Persist a pending approval record for a request."""
    record = ApprovalRecord(
        approval_request_id=request.approval_request_id,
        task_id=request.task_id,
        tenant_id=request.tenant_id,
        tool_call_id=request.tool_call_id,
        decision=ApprovalDecision.PENDING,
        payload_hash=request.payload_hash,
    )
    return repo.upsert_approval(record)


def record_decision(
    repo: Repository,
    approval_record_id: str,
    decision: ApprovalDecision,
    approver_id: str,
    channel: str,
) -> ApprovalRecord:
    record = repo.get_approval(approval_record_id)
    if record is None:
        raise KeyError(f"Unknown approval record {approval_record_id}")
    updated = record.model_copy(
        update={
            "decision": decision.value,
            "approver_id": approver_id,
            "channel": channel,
            "decided_at": datetime.now(UTC),
        }
    )
    return repo.upsert_approval(updated)


def is_approved(record: ApprovalRecord, expected_payload: dict) -> bool:
    """An action may proceed only if its approval is APPROVED *and* the payload
    still hashes to the approved value."""
    decision = (
        record.decision
        if isinstance(record.decision, ApprovalDecision)
        else ApprovalDecision(record.decision)
    )
    return decision == ApprovalDecision.APPROVED and record.payload_hash == payload_hash(
        expected_payload
    )
