"""Worker entrypoint for Cloud Run Jobs / Worker Pools.

Two modes:
- ``USE_PUBSUB=true``: pull from the Pub/Sub subscription, process each task,
  ack on success, and rely on the subscription's DLQ for poison messages.
- otherwise: drain the in-process queue (local smoke checks).

Run with: ``python -m agent_mesh.worker.main``.
"""

from __future__ import annotations

import json
import os
import sys

from agent_mesh.services.dispatch import InProcessDispatcher, get_dispatcher
from agent_mesh.settings import get_settings
from agent_mesh.worker.runner import Worker


def _run_pubsub() -> None:  # pragma: no cover - needs google-cloud-pubsub + creds
    from google.cloud import pubsub_v1  # type: ignore

    settings = get_settings()
    subscriber = pubsub_v1.SubscriberClient()
    subscription = os.getenv(
        "TASK_SUBSCRIPTION",
        subscriber.subscription_path(settings.project_id, f"{settings.task_topic}-worker"),
    )
    worker = Worker()

    def callback(message: pubsub_v1.subscriber.message.Message) -> None:
        try:
            data = json.loads(message.data.decode("utf-8"))
            worker.process(data["task_id"])
            message.ack()
        except Exception as exc:  # noqa: BLE001 - nack so Pub/Sub retries / DLQs
            print(f"task processing failed: {exc}", file=sys.stderr)
            message.nack()

    future = subscriber.subscribe(subscription, callback=callback)
    print(f"worker listening on {subscription}")
    try:
        future.result()
    except KeyboardInterrupt:
        future.cancel()


def _run_inprocess() -> None:
    dispatcher = get_dispatcher()
    if not isinstance(dispatcher, InProcessDispatcher):
        raise RuntimeError("in-process mode requires the in-process dispatcher")
    worker = Worker()
    drained = 0
    while not dispatcher.empty():
        task_id = dispatcher.get(timeout=1)
        worker.process(task_id)
        drained += 1
    print(f"drained {drained} task(s)")


def main() -> None:
    if get_settings().use_pubsub:
        _run_pubsub()
    else:
        _run_inprocess()


if __name__ == "__main__":
    main()
