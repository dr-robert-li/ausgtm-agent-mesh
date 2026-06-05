"""DUR-03: Pub/Sub dispatch runtime validation + in-process fallback.

Two tests:
1. ``test_pubsub_publish_consume_roundtrip`` — emulator-gated integration test.
   Skipped unless ``PUBSUB_EMULATOR_HOST`` is set (and ``google-cloud-pubsub`` is
   installed), so ``make test`` stays green without gcloud. When the emulator is
   running it provisions the topic/subscription via the idempotent setup helper,
   publishes a task id via ``PubSubDispatcher.publish_task``, and asserts the
   worker callback path processes it (pull one message, run ``worker.process``).
   Re-running is safe because the setup helper swallows ``AlreadyExists``.
2. ``test_inprocess_fallback_drains`` — unconditional. With ``USE_PUBSUB`` unset
   the in-process dispatcher must still drain and be processed, proving the
   fallback is retained (DUR-03 wording).
"""

from __future__ import annotations

import importlib.util
import json
import os

import pytest

from agent_mesh.services.dispatch import InProcessDispatcher, PubSubDispatcher
from agent_mesh.services.task_service import request_from_mcp
from agent_mesh.settings import Settings
from agent_mesh.worker.runner import Worker

# Skip the emulator test cleanly when the emulator env var is absent OR when the
# google-cloud-pubsub dependency is not installed (minimal env). Both conditions
# keep the default suite green without gcloud.
_EMULATOR_HOST = os.getenv("PUBSUB_EMULATOR_HOST")
_PUBSUB_AVAILABLE = importlib.util.find_spec("google.cloud.pubsub_v1") is not None

emulator_required = pytest.mark.skipif(
    not (_EMULATOR_HOST and _PUBSUB_AVAILABLE),
    reason="requires PUBSUB_EMULATOR_HOST and google-cloud-pubsub (no live GCP)",
)


@emulator_required
def test_pubsub_publish_consume_roundtrip(repo, monkeypatch):
    """Publish a task id through PubSubDispatcher and assert the worker callback
    path processes it, against the local Pub/Sub emulator."""
    from google.cloud import pubsub_v1  # type: ignore

    from agent_mesh.services.pubsub_setup import ensure_topic_and_subscription

    monkeypatch.setenv("USE_PUBSUB", "true")
    monkeypatch.setenv("PROJECT_ID", "local-test")
    monkeypatch.setenv("TASK_TOPIC", "agent-mesh-tasks")
    settings = Settings()

    # Idempotent provisioning — re-running must not raise on AlreadyExists.
    topic_path, subscription_path = ensure_topic_and_subscription(settings)
    ensure_topic_and_subscription(settings)  # second call proves idempotency

    # Persist a read task in this repo so worker.process can run without a DB.
    from agent_mesh.services.task_service import TaskService

    svc = TaskService(repo=repo, dispatcher=PubSubDispatcher(settings))
    task = svc.create_task(
        request_from_mcp(
            tenant_id="t", client_slug="c", mcp_subject="svc", text="summarize notes"
        )
    )

    # Pull the published message and drive the same callback the worker uses.
    subscriber = pubsub_v1.SubscriberClient()
    response = subscriber.pull(
        request={"subscription": subscription_path, "max_messages": 1},
        timeout=15,
    )
    assert response.received_messages, "no message received from the worker subscription"

    worker = Worker(repo=repo)
    processed = []
    for received in response.received_messages:
        data = json.loads(received.message.data.decode("utf-8"))
        assert data["task_id"] == task.task_id
        processed.append(worker.process(data["task_id"]))
        subscriber.acknowledge(
            request={"subscription": subscription_path, "ack_ids": [received.ack_id]}
        )

    assert "completed" in processed
    assert repo.get_task(task.task_id).state == "completed"


def test_inprocess_fallback_drains(repo, monkeypatch):
    """With USE_PUBSUB unset, the in-process dispatcher drains and the task is
    processed — proving the fallback is retained (DUR-03)."""
    monkeypatch.delenv("USE_PUBSUB", raising=False)
    assert Settings().use_pubsub is False

    # Local dispatcher + repo-bound worker (mirror test_approval_gating's pattern).
    # We drain manually rather than calling _run_inprocess(), which reads the
    # process-wide singleton repo/worker rather than this test's repo fixture.
    dispatcher = InProcessDispatcher()
    from agent_mesh.services.task_service import TaskService

    svc = TaskService(repo=repo, dispatcher=dispatcher)
    task = svc.create_task(
        request_from_mcp(
            tenant_id="t", client_slug="c", mcp_subject="svc", text="summarize notes"
        )
    )
    assert not dispatcher.empty()

    worker = Worker(repo=repo)
    drained = 0
    while not dispatcher.empty():
        task_id = dispatcher.get(timeout=1)
        worker.process(task_id)
        drained += 1

    assert drained == 1
    assert repo.get_task(task.task_id).state == "completed"
