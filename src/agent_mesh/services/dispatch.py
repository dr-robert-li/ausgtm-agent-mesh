"""Task dispatch abstraction.

Ingress publishes a task id; the worker consumes it. In production this is
Pub/Sub (durable, with a DLQ) so >60-minute runs survive ingress restarts. For
local smoke checks an in-process queue lets a single host run ingress + worker.
"""

from __future__ import annotations

import json
import queue
from typing import Protocol

from agent_mesh.settings import Settings, get_settings


class Dispatcher(Protocol):
    def publish_task(self, task_id: str) -> None: ...


class InProcessDispatcher:
    """Thread-safe in-memory queue. Local dev only."""

    def __init__(self) -> None:
        self._q: queue.Queue[str] = queue.Queue()

    def publish_task(self, task_id: str) -> None:
        self._q.put(task_id)

    def get(self, timeout: float | None = None) -> str:
        return self._q.get(timeout=timeout)

    def empty(self) -> bool:
        return self._q.empty()


class PubSubDispatcher:
    """Cloud Pub/Sub publisher. Imported lazily so the package stays importable
    without google-cloud-pubsub installed."""

    def __init__(self, settings: Settings) -> None:
        from google.cloud import pubsub_v1  # type: ignore

        self._publisher = pubsub_v1.PublisherClient()
        self._topic = self._publisher.topic_path(settings.project_id, settings.task_topic)

    def publish_task(self, task_id: str) -> None:
        data = json.dumps({"task_id": task_id}).encode("utf-8")
        self._publisher.publish(self._topic, data).result(timeout=30)


_INPROC: InProcessDispatcher | None = None


def get_dispatcher(settings: Settings | None = None) -> Dispatcher:
    settings = settings or get_settings()
    if settings.use_pubsub:
        return PubSubDispatcher(settings)
    global _INPROC
    if _INPROC is None:
        _INPROC = InProcessDispatcher()
    return _INPROC
