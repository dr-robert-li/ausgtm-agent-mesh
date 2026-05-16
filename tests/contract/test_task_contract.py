"""Task contract round-trip + extras-forbidden sanity."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from packages.contracts.task import Task, TaskEntrypoint, TaskProvenance


def _minimal_task() -> Task:
    return Task(
        tenant_id="tenant_test",
        entrypoint=TaskEntrypoint.slack,
        actor="U12345",
        goal="say hello",
        provenance=TaskProvenance(created_by="apps.slack"),
    )


def test_task_roundtrip() -> None:
    t = _minimal_task()
    again = Task.model_validate(t.model_dump(mode="json"))
    assert again.task_id == t.task_id
    assert again.goal == "say hello"


def test_task_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Task.model_validate(
            {
                "tenant_id": "tenant_test",
                "entrypoint": "slack",
                "actor": "U12345",
                "goal": "x",
                "provenance": {"created_by": "test"},
                "not_a_real_field": True,
            }
        )
