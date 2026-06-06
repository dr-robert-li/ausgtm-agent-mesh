"""Tool Gateway loader and real execution engine.

The gateway reads a tool pack manifest (YAML), validates each tool's declared
category against its approval requirement, and exposes a registry the agents can
consult. ``ToolGateway.execute(call)`` is the single chokepoint that resolves the
credential at call time (never returning it to the graph/agent — D-02), validates
the input/output boundary (04-02), dispatches to the registered adapter via the
derived dispatch key (or degrades to the deterministic stub when no
adapter/credential is present — D-11), and emits one OTel tool-event span (D-10).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from agent_mesh.contracts.enums import WRITE_CATEGORIES, ToolCategory

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agent_mesh.contracts.models import ToolCall
    from agent_mesh.tools.credentials import CredentialResolver


@dataclass(frozen=True)
class ToolSpec:
    name: str
    provider: str
    category: ToolCategory
    description: str
    approval_required: bool
    credential_secret_name: str | None
    resource_bindings: dict[str, Any]
    # --- D-03 fields (declared in the manifest; the stub loader dropped them) ---
    # integration_style drives the validator branch (04-02) AND, for aggregators
    # only, the adapter dispatch key (see adapters.adapter_key_for).
    integration_style: str = "direct_api"
    # Manifest-relative (or absolute) JSON-Schema paths. validation._load reads the
    # path directly, so execute() anchors a relative ref against the gateway's
    # base_dir (the manifest's parent) before passing it on — CWD is NOT the repo
    # root in a Cloud Run Job (04-02 handoff).
    input_schema_ref: str | None = None
    output_schema_ref: str | None = None

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
            integration_style=raw.get("integration_style", "direct_api"),
            input_schema_ref=raw.get("input_schema_ref"),
            output_schema_ref=raw.get("output_schema_ref"),
        )
        spec.validate()
        specs.append(spec)
    return specs


class ToolGateway:
    """Registry + stub executor for the loaded tool pack."""

    def __init__(self, specs: list[ToolSpec], *, manifest_dir: Path | None = None) -> None:
        self._specs = {s.name: s for s in specs}
        # Directory of the loaded manifest, used to anchor REPO-ROOT-RELATIVE schema
        # refs (e.g. "schemas/..."). validation._load reads the ref directly, so the
        # engine MUST hand it a CWD-resolvable/absolute path (04-02 handoff) — CWD is
        # NOT the repo root in a Cloud Run Job. None for a directly-constructed gateway
        # (aggregator specs carry no refs, so anchoring is a no-op for them).
        self._manifest_dir = manifest_dir.resolve() if manifest_dir is not None else None

    @classmethod
    def from_manifest(cls, path: str | Path) -> ToolGateway:
        manifest = Path(path)
        return cls(load_tool_pack(manifest), manifest_dir=manifest.parent)

    def get(self, name: str) -> ToolSpec:
        return self._specs[name]

    def list_tools(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def _resolve_ref(self, ref: str | None) -> str | None:
        """Anchor a repo-root-relative schema ref so validation._load reads it
        regardless of the process CWD (04-02 handoff; Cloud Run Job CWD != repo root).

        Manifest schema refs are relative to the REPO ROOT (e.g. "schemas/..."), and
        the manifest itself may live in a subdir (``manifests/``). Rather than assume
        a fixed depth, walk up from the manifest dir to the first ancestor where the
        ref resolves to an existing file. Absolute refs, the no-manifest-dir path
        (directly-constructed gateway), and refs that resolve under no ancestor pass
        through unchanged (the latter then surfaces as a normal validation error, not
        a silent mis-anchor).
        """
        if ref is None or self._manifest_dir is None:
            return ref
        p = Path(ref)
        if p.is_absolute():
            return ref
        for base in (self._manifest_dir, *self._manifest_dir.parents):
            candidate = base / p
            if candidate.exists():
                return str(candidate)
        return ref

    def _stub_result(self, spec: ToolSpec, parameters: dict[str, Any]) -> dict[str, Any]:
        """The deterministic no-creds / no-adapter fallback (D-11).

        Exact shape preserved from the original stub so the default suite and the
        approval-flow E2E stay green without any real SaaS credentials.
        """
        return {
            "tool": spec.name,
            "provider": spec.provider,
            "category": spec.category.value,
            "stub": True,
            "note": "POC stub result; no real SaaS call was made.",
            "echo_parameters": parameters,
        }

    def execute(
        self,
        call: ToolCall,
        *,
        resolver: CredentialResolver | None = None,
    ) -> dict[str, Any]:
        """Execute a tool call: resolve -> validate input -> dispatch -> validate
        output -> span (the real engine).

        Carries the ``ToolCall`` (not ``name, parameters``) so the span, resolver,
        and any failed-row have task/tenant correlation (Pitfall 2). The credential
        is resolved ONLY here and is NEVER placed in the returned dict, a span
        attribute, or a log (D-02). When no resolver is supplied (or the secret is
        absent) or no adapter is registered, the call degrades to the deterministic
        stub (D-11), keeping the default lane green and creds-free.
        """
        # Lazy imports keep gateway.py importable without these collaborators on a
        # bare path and avoid import cycles (validation/adapters/observability).
        from agent_mesh.observability import tool_event_span
        from agent_mesh.tools import validation
        from agent_mesh.tools.adapters import adapter_key_for, get_adapter

        spec = self.get(call.tool_name)
        params = call.parameters
        # Record the integration_style on the call for the audit row (D-03/D).
        call.integration_style = spec.integration_style
        approval_state = "approved" if spec.approval_required else "n/a"

        with tool_event_span(
            tenant_id=call.tenant_id,
            task_id=call.task_id,
            requester_id=call.requester_id,
            tool=spec.name,
            provider=spec.provider,
            category=spec.category.value,
            integration_style=spec.integration_style,
            approval_state=approval_state,
        ) as span:
            # (1) Resolve the credential at call time ONLY. Never returned/leaked.
            credential = resolver.resolve(spec.credential_secret_name) if resolver else None

            # (2) Validate input pre-call (04-02 fail-closed direct-only, D-04/D-06).
            #     An input violation is a HARD reject: no adapter call (D-06).
            try:
                validation.validate_tool_input(
                    integration_style=spec.integration_style,
                    input_schema_ref=self._resolve_ref(spec.input_schema_ref),
                    runtime_schema=None,
                    params=params,
                )
            except validation.InputSchemaViolation as exc:
                call.schema_validation = "input_rejected"
                if span is not None:
                    span.set_attribute("outcome", "input_rejected")
                return {
                    "tool": spec.name,
                    "provider": spec.provider,
                    "category": spec.category.value,
                    "outcome": "input_rejected",
                    "error": str(exc),
                }

            # (3) Select the adapter via the derived dispatch key. No adapter or no
            #     credential -> deterministic stub (D-11).
            adapter = get_adapter(adapter_key_for(spec))
            if adapter is None or credential is None:
                call.schema_validation = "ok"
                if span is not None:
                    span.set_attribute("outcome", "stub")
                return self._stub_result(spec, params)

            # (4) Call the adapter. The credential is passed by keyword and dropped
            #     when execute() returns; it never enters the result dict.
            result = adapter(spec, params, credential=credential)

            # (5) Validate output post-call. A violation QUARANTINES (the SaaS call
            #     already ran) rather than discarding the fact it ran (D-06).
            messages: list[str] = []
            if spec.output_schema_ref is not None:
                from agent_mesh.tools.validation import _load, validate_output

                messages = validate_output(
                    _load(self._resolve_ref(spec.output_schema_ref)), result
                )
            if messages:
                call.schema_validation = "output_quarantined"
                if span is not None:
                    span.set_attribute("outcome", "output_quarantined")
                return {
                    "tool": spec.name,
                    "provider": spec.provider,
                    "category": spec.category.value,
                    "outcome": "output_quarantined",
                    "quarantine_messages": messages,
                    "result": result,
                }

            call.schema_validation = "ok"
            if span is not None:
                span.set_attribute("outcome", "ok")
            return result
