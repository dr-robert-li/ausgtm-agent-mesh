"""Shared types for the model gateway."""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol


class ModelProvider(str, Enum):
    anthropic = "anthropic"  # PRIMARY (direct Claude Agent SDK)
    bedrock = "bedrock"      # fallback
    vertex = "vertex"        # fallback


class ModelRequest(Protocol):
    tier: str            # "S" | "M" | "L"
    system: str | None
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None
    max_tokens: int


class ModelResponse(Protocol):
    provider: ModelProvider
    model: str
    output: dict[str, Any]
    usage: dict[str, int]
