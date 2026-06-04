"""HTTP ingress (Cloud Run services).

A single FastAPI app exposes the internal API, Slack ingress, MCP ingress, and
approval callbacks. Slack and MCP both call the shared ``TaskService`` so their
capabilities are mirrored.
"""
