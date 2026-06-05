"""Idempotent Pub/Sub topic + worker-subscription provisioning.

DUR-03 transport provisioning. The dispatch path itself (publish via
``PubSubDispatcher.publish_task`` and consume via ``worker/main.py:_run_pubsub``)
already exists; this helper only ensures the topic and the ``{task_topic}-worker``
subscription that the worker pulls from exist, so the runtime path can be validated
end-to-end against the local Pub/Sub emulator (no live GCP) and re-run safely.

The clients auto-honor ``PUBSUB_EMULATOR_HOST`` (e.g. ``localhost:8085``), so the
same helper provisions against the emulator locally and against real Pub/Sub at
deploy time. ``google-cloud-pubsub`` and ``google-api-core`` are imported lazily
inside the helper (mirroring ``dispatch.py``) so the package stays importable in a
minimal environment without those dependencies.

This helper only provisions transport; it does NOT alter the dispatch contract
(``publish_task(task_id)`` + persist-before-publish ordering), keeping the path
Temporal-ready.
"""

from __future__ import annotations

from agent_mesh.settings import Settings, get_settings


def ensure_topic_and_subscription(settings: Settings | None = None) -> tuple[str, str]:
    """Idempotently create the task topic and ``{task_topic}-worker`` subscription.

    Uses the same ``project_id``/``task_topic`` as ``PubSubDispatcher`` and the
    same ``{task_topic}-worker`` subscription name as ``worker/main.py:_run_pubsub``.
    Swallows ``google.api_core.exceptions.AlreadyExists`` so a second invocation
    converges to the same transport state without raising. Other errors propagate
    (the catch is intentionally narrow so re-runs are safe without masking real
    failures).

    Returns ``(topic_path, subscription_path)``.
    """
    settings = settings or get_settings()

    # Lazy imports: keep ``import agent_mesh.services.pubsub_setup`` safe in
    # minimal envs that have neither google-cloud-pubsub nor google-api-core.
    from google.api_core.exceptions import AlreadyExists  # type: ignore
    from google.cloud import pubsub_v1  # type: ignore

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    topic_path = publisher.topic_path(settings.project_id, settings.task_topic)
    subscription_path = subscriber.subscription_path(
        settings.project_id, f"{settings.task_topic}-worker"
    )

    # google-cloud-pubsub 2.x admin API: keyword args name=/topic=.
    try:
        publisher.create_topic(name=topic_path)
    except AlreadyExists:
        pass

    try:
        subscriber.create_subscription(name=subscription_path, topic=topic_path)
    except AlreadyExists:
        pass

    return topic_path, subscription_path
