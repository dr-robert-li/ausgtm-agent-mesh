"""GCP Vertex AI fallback adapter.

Enabled via VERTEX_ENABLED=true; auth via GOOGLE_APPLICATION_CREDENTIALS.
"""

from __future__ import annotations


async def run_vertex_agent(*args, **kwargs):  # type: ignore[no-untyped-def]
    raise NotImplementedError("vertex_adapter is a scaffold placeholder")
