"""Slack Bolt app stub (Socket Mode for local dev).

Boundary: this app is a UI on top of the API. It MUST NOT:
  - import packages.workflows / packages.activities
  - call the Tool Gateway directly
  - touch the DB
It POSTs Task creations and HITL decisions to apps.api.
"""

from __future__ import annotations

import asyncio
import logging
import os

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

logger = logging.getLogger(__name__)

app = AsyncApp(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)


@app.event("app_mention")
async def handle_mention(event: dict, say) -> None:  # type: ignore[no-untyped-def]
    # TODO: extract goal, POST to apps.api `/v1/tasks`, ack with the task_id.
    user = event.get("user")
    await say(f"Hi <@{user}> — the mesh is up but no task routing is wired yet.")


async def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(main())
