"""MCP server stub.

External agents and self-loopback enter via this server. Like the Slack app,
the MCP server is a *client* of apps.api — it does not own state and does
not call the Tool Gateway directly.
"""

from __future__ import annotations

import asyncio
import logging
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server

logger = logging.getLogger(__name__)

server: Server = Server("ausgtm-agent-mesh")


# TODO: register tools that map to apps.api endpoints, e.g.:
#   - submit_task(goal, inputs) -> task_id
#   - get_task(task_id) -> Task
#   - decide_hitl(task_id, decision) -> Task
# All implementations call the API over HTTP — never the DB or Temporal.


async def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
