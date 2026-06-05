"""Approval gating for write actions.

Every write-category tool call and every applied prompt-to-code patch must pass
through here. The payload hash binds an approval to the *exact* action proposed,
so an approval cannot be replayed against a mutated payload.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import UTC, datetime

from agent_mesh.contracts.enums import WRITE_CATEGORIES, ApprovalDecision, ToolCategory
from agent_mesh.contracts.models import (
    ApprovalRecord,
    ApprovalRequest,
    ToolCall,
)
from agent_mesh.services.repository import Repository

# Task-metadata key under which the worker durably stashes issued HMAC approval
# tokens (keyed by approval_record_id) pending a real Slack/MCP postback channel.
# It is a bearer secret: anyone holding the token can self-approve a gated write,
# so it MUST be redacted from every task-read serialization (see
# api.serialization.public_task_dict). Defined here so the writer (worker.runner)
# and the readers (api.app, api.mcp_server) share one source of truth — adding a
# new read path must reuse the redactor, not re-derive this literal.
APPROVAL_TOKENS_METADATA_KEY = "approval_tokens"


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


_DEFAULT_TOKEN_TTL_S = 3600


def _approval_secret(secret: str | None) -> str:
    """Resolve the signing secret: explicit arg wins, else the environment.

    Returns the empty string when nothing is configured. Issuance tolerates the
    empty secret (it just mints a token that cannot verify); verification FAILS
    CLOSED on it (see ``verify_approval_token``)."""
    if secret is not None:
        return secret
    return os.getenv("APPROVAL_SIGNING_SECRET", "")


def _sign_approval(
    secret: str, *, record_id: str, payload_hash: str, requester_id: str, exp: int
) -> str:
    basestring = f"{record_id}:{payload_hash}:{requester_id}:{exp}".encode()
    return hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()


def issue_approval_token(
    record: ApprovalRecord,
    requester_id: str,
    *,
    ttl_s: int = _DEFAULT_TOKEN_TTL_S,
    secret: str | None = None,
) -> str:
    """Mint an HMAC-signed approval token binding the approver to exactly this
    approval record / task / payload, with an expiry.

    Format: ``{record_id}.{requester_id}.{exp}.{sig}`` where
    ``sig = HMAC-SHA256(secret, "{record_id}:{payload_hash}:{requester_id}:{exp}")``.

    Issuance NEVER raises when no secret is configured: it signs with the empty
    string, producing a token that ``verify_approval_token`` will reject (fail
    closed lives in verify). This keeps the live ``open_approval`` pause path —
    and the existing gating tests that exercise it without a secret — working.
    """
    secret_val = _approval_secret(secret)
    exp = int(time.time()) + int(ttl_s)
    sig = _sign_approval(
        secret_val,
        record_id=record.approval_record_id,
        payload_hash=record.payload_hash,
        requester_id=requester_id,
        exp=exp,
    )
    return f"{record.approval_record_id}.{requester_id}.{exp}.{sig}"


def verify_approval_token(
    token: str,
    record: ApprovalRecord,
    *,
    secret: str | None = None,
) -> str | None:
    """Verify an approval token against a loaded approval record.

    Returns the token's ``requester_id`` (the ONLY trusted approver identity) on
    success, else ``None``. FAILS CLOSED: returns ``None`` when no signing secret
    is configured — the deliberate divergence from ``slack_verify`` (which fails
    open in dev). Also returns ``None`` on a malformed token, a record-id
    mismatch (binds the token to exactly one approval record/task → cross-task
    replay defense), expiry, or an HMAC mismatch.
    """
    secret_val = _approval_secret(secret)
    if not secret_val:
        return None  # FAIL CLOSED — no secret, no approval.
    if not token:
        return None
    try:
        head, exp_str, sig = token.rsplit(".", 2)
        record_id, requester_id = head.split(".", 1)
    except ValueError:
        return None
    if record_id != record.approval_record_id:
        return None  # SEC-02b: a token for task A cannot approve task B.
    try:
        exp = int(exp_str)
    except ValueError:
        return None
    if time.time() > exp:
        return None  # Expired.
    expected = _sign_approval(
        secret_val,
        record_id=record.approval_record_id,
        payload_hash=record.payload_hash,
        requester_id=requester_id,
        exp=exp,
    )
    if not hmac.compare_digest(expected, sig):
        return None
    return requester_id


def open_approval(
    repo: Repository, request: ApprovalRequest
) -> tuple[ApprovalRecord, str]:
    """Persist a pending approval record and issue its approval token.

    Returns ``(record, token)``. The token binds the requester to exactly this
    record/task/payload; callers thread it to the requester so the approval
    callback can present it. Both callers MUST unpack the tuple."""
    record = ApprovalRecord(
        approval_request_id=request.approval_request_id,
        task_id=request.task_id,
        tenant_id=request.tenant_id,
        tool_call_id=request.tool_call_id,
        decision=ApprovalDecision.PENDING,
        payload_hash=request.payload_hash,
    )
    stored = repo.upsert_approval(record)
    token = issue_approval_token(stored, request.requester_id)
    return stored, token


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
