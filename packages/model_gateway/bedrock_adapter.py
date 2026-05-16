"""AWS Bedrock fallback adapter.

Enabled via BEDROCK_ENABLED=true; AWS creds via standard chain.
"""

from __future__ import annotations


async def run_bedrock_agent(*args, **kwargs):  # type: ignore[no-untyped-def]
    raise NotImplementedError("bedrock_adapter is a scaffold placeholder")
