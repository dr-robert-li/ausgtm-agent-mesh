"""Temporal worker entrypoint.

Hosts workflows from packages.workflows and activities from packages.activities.
Workflows MUST be deterministic and MUST NOT call agent SDKs, tools, or
databases directly — those live in activities.
"""

from __future__ import annotations

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

# from packages.workflows import ALL_WORKFLOWS
# from packages.activities import ALL_ACTIVITIES

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    task_queue = os.environ.get("TEMPORAL_TASK_QUEUE", "ausgtm-mesh")

    client = await Client.connect(host, namespace=namespace)

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[],  # ALL_WORKFLOWS once defined
        activities=[],  # ALL_ACTIVITIES once defined
    )
    logger.info("ausgtm-mesh worker started on %s/%s queue=%s", host, namespace, task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
