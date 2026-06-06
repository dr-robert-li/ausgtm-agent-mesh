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
from agent_mesh.tools.gateway import ToolGateway
from agent_mesh.worker.runner import Worker

# Tool pack manifest the worker loads its tool registry from (audit item B). The
# gateway resolves credentials at execution time via the Worker's resolver (default
# EnvCredentialResolver, creds-free by default); agents never receive raw credentials.
_TOOL_PACK_MANIFEST = os.getenv("TOOL_PACK_MANIFEST", "manifests/tool_pack_manifest.yaml")


def _build_worker() -> Worker:
    """Construct the live Worker with a real manifest-loaded ToolGateway (item B).

    Both bootstrap paths share this so the worker boots with a real gateway +
    resolver instead of ``tool_gateway=None`` (which silently stubbed every call).
    """
    return Worker(tool_gateway=ToolGateway.from_manifest(_TOOL_PACK_MANIFEST))


def _run_pubsub() -> None:  # pragma: no cover - needs google-cloud-pubsub + creds
    from google.cloud import pubsub_v1  # type: ignore

    settings = get_settings()
    subscriber = pubsub_v1.SubscriberClient()
    subscription = os.getenv(
        "TASK_SUBSCRIPTION",
        subscriber.subscription_path(settings.project_id, f"{settings.task_topic}-worker"),
    )
    worker = _build_worker()

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
    worker = _build_worker()
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
