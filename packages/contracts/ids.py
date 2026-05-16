"""ID helpers. Reference arch uses `{prefix}_{ULID}` everywhere."""

from __future__ import annotations

from ulid import ULID


def new_id(prefix: str) -> str:
    """Return a new `{prefix}_{ULID}` identifier.

    Examples:
        new_id("task")   -> "task_01HZX..."
        new_id("spawn")  -> "spawn_01HZX..."
    """
    if not prefix or "_" in prefix:
        raise ValueError("prefix must be non-empty and not contain underscores")
    return f"{prefix}_{ULID()}"
