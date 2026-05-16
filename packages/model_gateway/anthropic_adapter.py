"""Direct Anthropic Claude Agent SDK adapter (PRIMARY path).

This adapter is called from activities only. It must never see raw tool
credentials — the Tool Gateway is the sole credential holder.
"""

from __future__ import annotations

# from anthropic import AsyncAnthropic  # imported when the adapter is implemented


async def run_claude_agent(*args, **kwargs):  # type: ignore[no-untyped-def]
    """Placeholder. Real implementation will:
    - Resolve the model id from the requested tier (S/M/L) and policy.
    - Construct messages + tool handles (NOT credentials).
    - Stream the agent loop, surfacing tool-use to the Tool Gateway.
    - Return a normalized ModelResponse.
    """
    raise NotImplementedError("anthropic_adapter is a scaffold placeholder")
