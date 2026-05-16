"""Temporal workflow definitions. Deterministic. No I/O, no clocks, no RNG.

Workflows call activities for all side effects, including every model
provider call (Anthropic / Bedrock / Vertex) via packages.model_gateway and
every tool call via packages.tool_gateway.
"""

ALL_WORKFLOWS: list = []
