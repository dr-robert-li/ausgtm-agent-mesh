"""Shared service layer.

Both ingress (Slack, MCP, API) and the worker call into this layer so Slack and
MCP capabilities stay mirrored and the orchestrator stays the source of truth.
"""
