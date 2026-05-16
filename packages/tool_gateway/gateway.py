"""Tool Gateway entrypoint (scaffold)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolHandle:
    """Opaque reference to a tool. Activities pass these around; only the
    Tool Gateway resolves them to real clients with credentials attached."""

    name: str           # e.g. "slack.post_message", "monday.read_board"
    trust_tier: str     # see packages.contracts.policy.ToolTrustTier


class ToolGateway:
    """Single source of truth for tool credentials and tool execution.

    Not implemented yet; this is a placeholder showing the intended seam.
    """

    async def call(
        self,
        handle: ToolHandle,
        payload: dict[str, Any],
        *,
        caller_max_trust_tier: str,
    ) -> dict[str, Any]:
        raise NotImplementedError("tool_gateway scaffold")
