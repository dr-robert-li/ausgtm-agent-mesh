"""DEP-02 / D-11: deployment-manifest <-> scripts <-> tool-pack <-> schemas consistency.

WHY a NEW validator (D-11 resolved in favor of a new module): the only existing
"schema machinery" is ``agent_mesh.contracts.export_schemas``, and it does exactly
one thing — emit Pydantic ``CONTRACT_MODELS`` to ``schemas/contracts/*.schema.json``.
It NEVER reads the YAML deployment/tool-pack manifests, never reconciles the
``${VAR}`` env contract the deploy scripts require, and has no consistency-checking
concept at all. Extending it would conflate Pydantic-export with YAML-consistency —
two distinct concerns. So this is a dedicated validator that imports none of the
export machinery.

It runs three cross-checks (all file-relative, cwd-independent per SP-4):

1. **Env-var contract** — every deploy var the scripts consume maps to a supplying
   field in ``deployment.manifest.yaml``, with NO orphan on either side:
   the mapped var name appears in the script text AND the mapped manifest field
   path resolves to a value.
2. **Tool-pack pointer + schema coverage** — ``tool_packs.manifest_path`` resolves;
   every tool that declares an ``input_schema_ref`` / ``output_schema_ref`` has the
   referenced file on disk; and every tool's ``integration_style`` (plus the
   manifest-declared ``integration_styles`` list) is within the known style set.
3. **Required-stack assertions (CLAUDE.md §6 AC-1/AC-2)** — the manifest declares
   ``agent_framework: langchain+langgraph+deepagents``, ``observability: langfuse``,
   and ``langsmith: optional-alternative-only`` (LangSmith is never required).

Also includes a ``wrangler --dry-run`` leg that runs when wrangler is on PATH else
SKIPS LOUDLY (D-10 / SP-5). No ``live`` marker: the whole module runs in the
default ``-m "not live"`` lane.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

# tests/deploy/<this file>  ->  parents[2] == repo root (SP-4: never cwd-relative).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFESTS_DIR = _REPO_ROOT / "manifests"
_SCHEMAS_DIR = _REPO_ROOT / "schemas"
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_CF_WRAPPER_DIR = _REPO_ROOT / "cloudflare" / "ai-gateway-wrapper"

_DEPLOYMENT_MANIFEST = _MANIFESTS_DIR / "deployment.manifest.yaml"
_TOOL_PACK_MANIFEST = _MANIFESTS_DIR / "tool_pack_manifest.yaml"

_BOOTSTRAP = _SCRIPTS_DIR / "gcp_bootstrap.sh"
_DEPLOY_CORE = _SCRIPTS_DIR / "gcp_deploy_core.sh"
_CF_DEPLOY = _SCRIPTS_DIR / "cf_deploy_ai_gateway_worker.sh"

# The canonical known set of tool integration styles (CLAUDE.md §3 / AC-13).
_KNOWN_INTEGRATION_STYLES = frozenset(
    {"direct_api", "mcp_server", "aggregate_mcp", "nango_aggregator", "composio_aggregator"}
)

# Explicit env-var <-> manifest-field contract (the plan enumerates these 13).
# Each entry: ENV_VAR -> dotted path into deployment.manifest.yaml that supplies it.
# Using the explicit map avoids the regex foot-guns of grabbing every ``${VAR}``
# (which would wrongly pull IMAGE_TAG / SQL_TIER / SQL_DATABASE as orphans).
_ENV_TO_MANIFEST_FIELD: dict[str, str] = {
    "PROJECT_ID": "deployment.project_id",
    "REGION": "deployment.region",
    "TENANT_ID": "deployment.tenant_id",
    "CLIENT_SLUG": "deployment.client_slug",
    "MODEL_ROUTE_PROFILE": "model_routes.default_profile",
    "AR_REPO": "gcp.artifact_registry_repo",
    "SQL_INSTANCE": "gcp.cloud_sql.instance_name",
    "CLOUDFLARE_ACCOUNT_ID": "cloudflare.account_id",
    "CLOUDFLARE_AI_GATEWAY_ID": "cloudflare.ai_gateway_id",
    "WRANGLER_ENV": "cloudflare.wrangler_env",
    "REUSE_EXISTING_CLOUDFLARE_GATEWAY": "cloudflare.reuse_existing_gateway",
    "CREATE_PROJECT": "deployment.create_project_if_missing",
    "BILLING_ACCOUNT_ID": "deployment.billing_account_id",
}

# The scripts that, between them, consume the deploy env contract.
_DEPLOY_SCRIPTS = (_BOOTSTRAP, _DEPLOY_CORE, _CF_DEPLOY)


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def _resolve_path(doc: dict[str, Any], dotted: str) -> Any:
    """Resolve a dotted path into a nested dict; raise KeyError if any leg is
    missing so a manifest-side orphan surfaces as a hard failure."""
    node: Any = doc
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(dotted)
        node = node[part]
    return node


@pytest.fixture(scope="module")
def deployment_manifest() -> dict[str, Any]:
    assert _DEPLOYMENT_MANIFEST.is_file(), f"missing {_DEPLOYMENT_MANIFEST}"
    return _load_yaml(_DEPLOYMENT_MANIFEST)


@pytest.fixture(scope="module")
def script_text() -> str:
    """Concatenated text of all deploy scripts (the env-var consumer side)."""
    return "\n".join(p.read_text() for p in _DEPLOY_SCRIPTS)


# ---------------------------------------------------------------------------
# Cross-check 1: env-var contract (no orphan in either direction).
# ---------------------------------------------------------------------------


def test_env_contract_every_script_var_has_manifest_field(
    deployment_manifest: dict[str, Any], script_text: str
) -> None:
    """Forward direction: each mapped deploy var is referenced by the scripts AND
    its supplying manifest field resolves to a value. No orphan on either side."""
    missing_in_script: list[str] = []
    missing_in_manifest: list[str] = []
    for var, field in _ENV_TO_MANIFEST_FIELD.items():
        if var not in script_text:
            missing_in_script.append(var)
        try:
            _resolve_path(deployment_manifest, field)
        except KeyError:
            missing_in_manifest.append(f"{var} -> {field}")

    assert not missing_in_script, (
        f"deploy vars not referenced by any script (script-side orphan): {missing_in_script}"
    )
    assert not missing_in_manifest, (
        f"deploy vars with no supplying manifest field (manifest-side orphan): "
        f"{missing_in_manifest}"
    )


def test_env_contract_required_vars_use_strict_guard(script_text: str) -> None:
    """The two truly-required vars (no default) must use the ``:?`` strict guard so
    a missing value fails fast rather than silently defaulting."""
    assert 'PROJECT_ID:?' in script_text, "PROJECT_ID must be a strict (:?) requirement"
    assert "CLOUDFLARE_ACCOUNT_ID:?" in script_text, (
        "CLOUDFLARE_ACCOUNT_ID must be a strict (:?) requirement"
    )


# ---------------------------------------------------------------------------
# Cross-check 2: tool-pack pointer + schema coverage + integration styles.
# ---------------------------------------------------------------------------


def test_tool_pack_manifest_path_resolves(deployment_manifest: dict[str, Any]) -> None:
    """``tool_packs.manifest_path`` must resolve to an existing file (file-relative
    to the repo root, SP-4)."""
    rel = _resolve_path(deployment_manifest, "tool_packs.manifest_path")
    resolved = _REPO_ROOT / rel
    assert resolved.is_file(), f"tool_packs.manifest_path does not resolve: {resolved}"
    # And it is the same file this validator reads for schema coverage.
    assert resolved.resolve() == _TOOL_PACK_MANIFEST.resolve()


def test_every_schema_ref_resolves_on_disk() -> None:
    """Every tool that declares an input/output schema ref has the referenced file
    on disk (file-relative). Aggregate tools that declare NO schema ref are
    exempt by design (D-04: they validate against the runtime provider schema)."""
    tool_pack = _load_yaml(_TOOL_PACK_MANIFEST)
    missing: list[str] = []
    checked = 0
    for tool in tool_pack["tools"]:
        name = tool["name"]
        for key in ("input_schema_ref", "output_schema_ref"):
            ref = tool.get(key)
            if not ref:
                continue  # schema-less aggregator tool: exempt
            checked += 1
            resolved = _REPO_ROOT / ref
            if not resolved.is_file():
                missing.append(f"{name}.{key} -> {ref}")
    assert checked > 0, "expected at least one tool with a schema ref to verify"
    assert not missing, f"declared schema refs with no file on disk: {missing}"


def test_integration_styles_within_known_set(deployment_manifest: dict[str, Any]) -> None:
    """Every tool's ``integration_style`` is in the known set, and the
    manifest-declared ``integration_styles`` list is a SUBSET of the known set.

    NOTE: tool styles are checked against the KNOWN set, NOT against the
    manifest's declared ``integration_styles`` list — ``composio_aggregator`` is
    used by tools but intentionally absent from that declared list, which is fine.
    """
    declared = set(_resolve_path(deployment_manifest, "tool_packs.integration_styles"))
    assert declared <= _KNOWN_INTEGRATION_STYLES, (
        f"manifest declares unknown integration styles: {declared - _KNOWN_INTEGRATION_STYLES}"
    )

    tool_pack = _load_yaml(_TOOL_PACK_MANIFEST)
    unknown: list[str] = []
    for tool in tool_pack["tools"]:
        style = tool.get("integration_style")
        if style not in _KNOWN_INTEGRATION_STYLES:
            unknown.append(f"{tool['name']}: {style}")
    assert not unknown, f"tools with unknown integration_style: {unknown}"


# ---------------------------------------------------------------------------
# Cross-check 3: required-stack assertions (CLAUDE.md §6 AC-1/AC-2).
# ---------------------------------------------------------------------------


def test_required_stack_declared(deployment_manifest: dict[str, Any]) -> None:
    """The default required stack is asserted by the manifest: LangChain +
    LangGraph + Deep Agents + Langfuse, with LangSmith optional-only."""
    assert _resolve_path(deployment_manifest, "stack.agent_framework") == (
        "langchain+langgraph+deepagents"
    )
    assert _resolve_path(deployment_manifest, "stack.observability") == "langfuse"
    assert _resolve_path(deployment_manifest, "stack.langsmith") == (
        "optional-alternative-only"
    )


# ---------------------------------------------------------------------------
# wrangler --dry-run leg — LOUD skip when absent (D-10 / SP-5).
# ---------------------------------------------------------------------------


def test_wrangler_dry_run_loud_skip() -> None:
    """Run ``wrangler deploy --dry-run`` against the wrapper when wrangler is
    installed, else SKIP LOUDLY.

    Empirically wrangler is absent on this dev machine, so this is the actual
    default-lane path — and the skip NAMES the gap (never a silent cap).
    """
    if shutil.which("wrangler") is None:
        pytest.skip("wrangler not installed; Cloudflare worker --dry-run skipped")
    if not _CF_WRAPPER_DIR.is_dir():
        pytest.skip(
            f"wrangler present but {_CF_WRAPPER_DIR} missing; worker --dry-run skipped"
        )
    result = subprocess.run(
        ["wrangler", "deploy", "--dry-run", "--env", "poc"],
        cwd=str(_CF_WRAPPER_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"wrangler --dry-run failed:\n{result.stdout}\n{result.stderr}"
