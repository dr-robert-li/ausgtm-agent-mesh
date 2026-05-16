"""Sanity check for the {prefix}_{ULID} ID helper."""

from __future__ import annotations

import pytest

from packages.contracts.ids import new_id


def test_new_id_has_prefix() -> None:
    task_id = new_id("task")
    assert task_id.startswith("task_")
    assert len(task_id) > len("task_")


def test_new_id_rejects_empty_prefix() -> None:
    with pytest.raises(ValueError):
        new_id("")


def test_new_id_rejects_underscore_prefix() -> None:
    with pytest.raises(ValueError):
        new_id("foo_bar")
