"""Tool Gateway loader and stub execution path.

The gateway reads a tool pack manifest (YAML), validates each tool's declared
category against its approval requirement, and exposes a registry the agents can
consult. Execution here is a *stub*: it returns a recorded placeholder result so
the end-to-end flow (including the approval gate) can be exercised without any
real SaaS credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agent_mesh.contracts.enums import WRITE_CATEGORIES, ToolCategory


@dataclass(frozen=True)
class ToolSpec:
    name: str
    provider: str
    category: ToolCategory
    description: str
    approval_required: bool
    credential_secret_name: str | None
    resource_bindings: dict[str, Any]

    def validate(self) -> None:
        """A write-class tool MUST declare approval_required=true."""
        if self.category in WRITE_CATEGORIES and not self.approval_required:
            raise ValueError(
                f"Tool {self.name!r} is category {self.category.value} but "
                "approval_required is false; write-class tools must require approval."
            )


def load_tool_pack(path: str | Path) -> list[ToolSpec]:
    data = yaml.safe_load(Path(path).read_text())
    specs: list[ToolSpec] = []
    for raw in data.get("tools", []):
        spec = ToolSpec(
            name=raw["name"],
            provider=raw.get("provider", "unknown"),
            category=ToolCategory(raw["category"]),
            description=raw.get("description", ""),
            approval_required=bool(raw.get("approval_required", False)),
            credential_secret_name=raw.get("credential_secret_name"),
            resource_bindings=raw.get("resource_bindings", {}),
        )
        spec.validate()
        specs.append(spec)
    return specs


class ToolGateway:
    """Registry + stub executor for the loaded tool pack."""

    def __init__(self, specs: list[ToolSpec]) -> None:
        self._specs = {s.name: s for s in specs}

    @classmethod
    def from_manifest(cls, path: str | Path) -> ToolGateway:
        return cls(load_tool_pack(path))

    def get(self, name: str) -> ToolSpec:
        return self._specs[name]

    def list_tools(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def execute(self, name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Stub execution. A real adapter would resolve the credential from
        Secret Manager and call the SaaS API. Write tools are only reached here
        AFTER an approval has been recorded by the caller."""
        spec = self.get(name)
        return {
            "tool": spec.name,
            "provider": spec.provider,
            "category": spec.category.value,
            "stub": True,
            "note": "POC stub result; no real SaaS call was made.",
            "echo_parameters": parameters,
        }
