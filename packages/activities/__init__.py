"""Temporal activities. Side-effecting work lives here.

Agent SDK calls (Anthropic Claude Agent SDK, Bedrock fallback, Vertex
fallback) are invoked from activities via packages.model_gateway.
External tool calls (Slack, Monday, Sheets, tl;dv) go through
packages.tool_gateway, which is the only holder of credentials.
"""

ALL_ACTIVITIES: list = []
