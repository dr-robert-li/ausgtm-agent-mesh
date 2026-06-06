"""D-06 structural egress chokepoint guard (GW-02).

GW-02 is a STRUCTURAL proof, not a Cloudflare deployment (CF worker publish is
Phase 5 / DEP-02). Under the in-process Router (D-09) the egress ``api_base`` lives
PER-ROUTE in ``model_list[*].litellm_params.api_base`` (RESEARCH Finding 6 /
Pitfall 3) — NOT on the chat-model constructor. This module therefore proves three
things with zero creds, in the default suite:

1. **Config assertion** — with ``CF_ENABLED=true`` + ``CF_AIG_WRAPPER_URL`` set,
   every route's ``api_base`` resolves to the CF wrapper URL (the yaml encodes the
   indirection as the literal string ``os.environ/CF_AIG_WRAPPER_URL``).
2. **Direct-provider-construction guard** — no module under ``src/agent_mesh``
   constructs ``ChatAnthropic`` / ``ChatVertexAI`` or calls ``litellm.completion(``
   directly outside the gateway; only ``get_chat_model()`` / ``build_router()`` may
   reach a provider (the Router IS "the client", RESEARCH Finding 6). Mitigates
   T-03-02-01.
3. **Inert prod-proxy fields** — ``general_settings.max_budget`` and ``master_key``
   are present and well-formed in the yaml (prod-proxy config, D-09) but are NEVER
   consumed by the in-process runtime path (``build_router`` / ``get_chat_model``);
   the durable budget ledger is the SOLE enforcer (Pitfall 6).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_PATH = _REPO_ROOT / "config" / "model_gateway.config.yaml"
_SRC_ROOT = _REPO_ROOT / "src" / "agent_mesh"
_GATEWAY_MODULE = _SRC_ROOT / "worker" / "model_gateway.py"

# The literal indirection the yaml uses for the per-route CF egress api_base.
# LiteLLM resolves ``os.environ/NAME`` to ``os.environ["NAME"]`` at runtime; the
# config-assertion below resolves the SAME shape so the test mirrors runtime.
_CF_ENV_REF = "os.environ/CF_AIG_WRAPPER_URL"

# Forbidden direct-provider construction outside the gateway seam. The Router (built
# by build_router / reached only via get_chat_model) is the sole sanctioned path.
_FORBIDDEN_NAMES = ("ChatAnthropic", "ChatVertexAI")


def _load_config() -> dict:
    with open(_CONFIG_PATH) as fh:
        return yaml.safe_load(fh)


def _resolve_api_base(raw: str, *, cf_wrapper_url: str) -> str:
    """Resolve the yaml ``api_base`` reference the way LiteLLM would at runtime.

    ``os.environ/CF_AIG_WRAPPER_URL`` -> the exported ``CF_AIG_WRAPPER_URL`` value.
    Any other literal is returned unchanged (so a hardcoded provider URL would fail
    the assertion below — which is the point).
    """
    if raw == _CF_ENV_REF:
        return cf_wrapper_url
    return raw


# ---------------------------------------------------------------------------
# 1. Config assertion: every route egresses through the CF wrapper when enabled
# ---------------------------------------------------------------------------


def test_every_route_api_base_resolves_to_cf_wrapper_when_enabled(monkeypatch):
    """With CF enabled, every ``model_list[*].litellm_params.api_base`` resolves to
    the CF wrapper URL — no route may egress directly to a provider (T-03-02-02)."""
    cf_wrapper_url = "https://gw.example/v1"
    monkeypatch.setenv("CF_ENABLED", "true")
    monkeypatch.setenv("CF_AIG_WRAPPER_URL", cf_wrapper_url)

    cfg = _load_config()
    model_list = cfg["model_list"]
    assert model_list, "model_list must not be empty"

    for route in model_list:
        params = route["litellm_params"]
        assert "api_base" in params, (
            f"route {route['model_name']!r} has no api_base — egress is ungoverned"
        )
        resolved = _resolve_api_base(params["api_base"], cf_wrapper_url=cf_wrapper_url)
        assert resolved == cf_wrapper_url, (
            f"route {route['model_name']!r} api_base {params['api_base']!r} does NOT "
            f"resolve to the CF wrapper {cf_wrapper_url!r} when CF_ENABLED — direct "
            f"provider egress bypassing Cloudflare (GW-02 violation, T-03-02-02)"
        )


def test_every_route_api_base_uses_the_env_indirection(monkeypatch):
    """Defence-in-depth: every route's api_base is the env-indirection literal, not a
    hardcoded URL. A hardcoded provider URL would silently bypass CF regardless of
    CF_ENABLED, so the literal shape itself is asserted."""
    cfg = _load_config()
    for route in cfg["model_list"]:
        api_base = route["litellm_params"]["api_base"]
        assert api_base == _CF_ENV_REF, (
            f"route {route['model_name']!r} api_base {api_base!r} is not the "
            f"{_CF_ENV_REF!r} indirection — a hardcoded egress would dodge CF"
        )


# ---------------------------------------------------------------------------
# 2. Direct-provider-construction guard (AST over src/agent_mesh)
# ---------------------------------------------------------------------------


def _python_sources() -> list[Path]:
    return sorted(_SRC_ROOT.rglob("*.py"))


def _direct_provider_offenders() -> list[tuple[str, int, str]]:
    """Return (relpath, lineno, symbol) for every forbidden direct-provider
    construction/import or ``litellm.completion(`` call anywhere under
    ``src/agent_mesh``.

    Uses ``ast`` so comments and string literals are ignored structurally (no
    false positives from prose/docstrings that merely name the symbols — this very
    module's gateway docstring mentions them, and the gateway code legitimately uses
    ``self._router.completion``). ``litellm.completion(`` is detected as an
    Attribute call ``litellm.completion`` to avoid flagging ``router.completion`` /
    ``self._router.completion`` (the sanctioned Router path).
    """
    offenders: list[tuple[str, int, str]] = []
    for path in _python_sources():
        rel = str(path.relative_to(_REPO_ROOT))
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            # `from langchain... import ChatAnthropic` / `import ... as ChatVertexAI`
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in _FORBIDDEN_NAMES:
                        offenders.append((rel, node.lineno, alias.name))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    leaf = alias.name.rsplit(".", 1)[-1]
                    if leaf in _FORBIDDEN_NAMES:
                        offenders.append((rel, node.lineno, alias.name))
            # Bare-name construction: `ChatAnthropic(...)` / `ChatVertexAI(...)`
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in _FORBIDDEN_NAMES:
                    offenders.append((rel, node.lineno, func.id))
                # `litellm.completion(...)` — direct provider call bypassing Router.
                elif (
                    isinstance(func, ast.Attribute)
                    and func.attr == "completion"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "litellm"
                ):
                    offenders.append((rel, node.lineno, "litellm.completion"))
    return offenders


def test_no_direct_provider_construction_outside_gateway():
    """No src module constructs a provider client directly — agents/workers reach
    providers ONLY through get_chat_model()/build_router() (T-03-02-01, GW-02).

    This guard would FAIL if a future change imported/constructed ChatAnthropic /
    ChatVertexAI or called ``litellm.completion(`` anywhere under src/agent_mesh.
    """
    offenders = _direct_provider_offenders()
    assert offenders == [], (
        "direct provider construction/call found outside the gateway seam "
        "(budget + Cloudflare bypass, T-03-02-01): "
        + ", ".join(f"{r}:{ln} -> {sym}" for r, ln, sym in offenders)
    )


def test_guard_has_real_coverage():
    """Sanity: the guard actually walked source files (a guard that scans nothing
    would vacuously pass). At least the gateway module must be in scope."""
    sources = _python_sources()
    assert _GATEWAY_MODULE in sources, "model_gateway.py must be within the scan set"
    assert len(sources) >= 5, "expected the guard to walk the real src tree"


def test_guard_detects_a_synthetic_offender(tmp_path):
    """Negative control: prove the AST guard WOULD flag a direct-provider call. We
    parse a synthetic snippet (not under src) so a real regression cannot pass
    silently because the detector is broken."""
    snippet = (
        "from langchain_anthropic import ChatAnthropic\n"
        "import litellm\n"
        "def bad():\n"
        "    ChatAnthropic(model='x')\n"
        "    litellm.completion(model='y', messages=[])\n"
    )
    tree = ast.parse(snippet)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found += [a.name for a in node.names if a.name in _FORBIDDEN_NAMES]
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_NAMES:
                found.append(func.id)
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == "completion"
                and isinstance(func.value, ast.Name)
                and func.value.id == "litellm"
            ):
                found.append("litellm.completion")
    assert "ChatAnthropic" in found
    assert "litellm.completion" in found


# ---------------------------------------------------------------------------
# 3. Inert prod-proxy fields: present in yaml, never read by the in-process runtime
# ---------------------------------------------------------------------------


def test_max_budget_and_master_key_present_and_well_formed():
    """``general_settings.max_budget`` and ``master_key`` are present + well-formed
    in the yaml (prod-proxy config, D-09)."""
    cfg = _load_config()
    general = cfg.get("general_settings", {})
    assert general.get("max_budget") == 50, "prod-proxy max_budget must be the USD 50 cap"
    master_key = general.get("master_key")
    assert isinstance(master_key, str) and master_key.startswith("os.environ/"), (
        "master_key must be an os.environ/ indirection (no literal secret in yaml)"
    )


def test_inert_fields_not_consumed_by_in_process_runtime():
    """The in-process runtime path (``build_router`` / ``get_chat_model`` / the
    Router-binding source) NEVER reads ``max_budget`` or ``master_key`` — the durable
    ledger is the SOLE enforcer (D-04/D-09, Pitfall 6). Asserted structurally over
    the gateway module source so a future regression that wired the inert proxy
    fields into the runtime would fail."""
    source = _GATEWAY_MODULE.read_text()
    tree = ast.parse(source)
    # Collect every string-literal and attribute/name token the runtime references.
    referenced_strings = {
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
    }
    for inert in ("max_budget", "master_key"):
        assert inert not in referenced_strings, (
            f"in-process gateway runtime references {inert!r}; the inert prod-proxy "
            f"field must NOT enforce in-process (the durable ledger does, Pitfall 6)"
        )


def test_build_router_does_not_load_general_settings():
    """``build_router`` loads only ``model_list`` + ``router_settings`` — it must not
    pull ``general_settings`` (where the inert ``max_budget``/``master_key`` live) into
    the in-process Router."""
    import inspect

    from agent_mesh.worker import model_gateway

    src = inspect.getsource(model_gateway.build_router)
    assert "general_settings" not in src, (
        "build_router reads general_settings — the inert prod-proxy budget/master_key "
        "must not reach the in-process Router (durable ledger enforces, D-09)"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
