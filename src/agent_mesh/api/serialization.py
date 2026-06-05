"""Public serialization for task records exposed over ingress endpoints.

The worker durably stashes issued HMAC approval tokens on ``TaskRecord.metadata``
(see ``worker.runner``). Those tokens are bearer secrets — holding one lets a
caller self-approve a write-gated tool call. Task-read endpoints are currently
unauthenticated and untenant-scoped, so a raw ``model_dump`` would hand the token
to any caller who knows a task id, defeating the SEC-01 write-gate (CR-01).

``public_task_dict`` is the single chokepoint every task-read path MUST use, so a
newly added read endpoint cannot silently reintroduce the leak.
"""

from __future__ import annotations

from typing import Any

from agent_mesh.contracts.models import TaskRecord
from agent_mesh.services.approvals import APPROVAL_TOKENS_METADATA_KEY


def public_task_dict(task: TaskRecord) -> dict[str, Any]:
    """JSON-safe TaskRecord dump with bearer secrets stripped from metadata.

    Removes the approval-token bundle so it never crosses an ingress boundary.
    Uses a defensive copy of ``metadata`` so the in-memory repository's stored
    record is not mutated as a side effect.
    """
    data = task.model_dump(mode="json")
    metadata = data.get("metadata")
    if isinstance(metadata, dict) and APPROVAL_TOKENS_METADATA_KEY in metadata:
        redacted = dict(metadata)
        redacted.pop(APPROVAL_TOKENS_METADATA_KEY, None)
        data["metadata"] = redacted
    return data
