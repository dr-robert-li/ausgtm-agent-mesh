"""COMPOSE-03 static-validation of the full-stack ``docker-compose.yml``.

The ONLY CI-wired Phase-10 artifact. It shells out to ``docker compose config``,
which is **daemon-free** — it resolves, merges, interpolates, and prints the
rendered config (even with ``build:`` services) without contacting the Docker
daemon or bringing anything up. So this is a pure static parse/shape assertion:
it proves the compose file *parses and declares the expected set*, NOT that the
stack *works* at runtime (bind-source existence, ``api_base`` correctness, and
actual migration application are explicitly out of scope — Pitfall 3; the
RUNBOOK documents the operator-only runtime proofs).

Skip shape (CRITICAL — differs from the ``pg_dsn`` fixture): a **module-level**
``pytestmark = pytest.mark.skipif(shutil.which("docker") is None, ...)`` so the
WHOLE file loud-skips before any subprocess runs when the ``docker`` binary is
absent. This mirrors the executor's own ``shutil.which("docker")`` gate
(``src/agent_mesh/sandbox/executor.py``). It is NOT ``live``-marked, so it
auto-collects under plain ``make test`` (``pytest -q -m "not live"``) and
passes-or-loud-skips on any box.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

# Repo root = the directory holding docker-compose.yml (two levels up from this
# file: tests/ -> repo root).
REPO_ROOT = Path(__file__).resolve().parent.parent

# Module-level loud-skip: gate the whole file on the docker CLI binary (not a
# DSN env var, and not a fixture-internal skip). Same loud-skip PRINCIPLE as the
# pg_dsn fixture; different mechanism (module-level skipif vs fixture pytest.skip).
pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="docker binary absent; compose-config validation requires the docker CLI",
)


def _compose_config(*profile_args: str, services: bool = False) -> str:
    """Run ``docker compose config`` (daemon-free) at the repo root and return
    its rendered stdout. ``check=True`` so a malformed file fails loudly.

    ``profile_args`` are extra ``--profile NAME`` tokens; ``services=True``
    switches to ``config --services`` (one service name per line).
    """
    cmd = ["docker", "compose", *profile_args, "config"]
    if services:
        cmd.append("--services")
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def _services(*profile_args: str) -> set[str]:
    out = _compose_config(*profile_args, services=True)
    return {line.strip() for line in out.splitlines() if line.strip()}


def test_bare_compose_config_parses() -> None:
    """The bare ``docker compose config`` resolves/merges/interpolates with
    exit 0 — the file is structurally valid (a malformed file raises via
    check=True)."""
    rendered = _compose_config()
    assert rendered, "rendered compose config was empty"


def test_core_services_present_and_litellm_absent() -> None:
    """Core services are declared; there is NO standalone litellm container
    (D-06 — the in-process litellm.Router IS the model control plane). ``migrate``
    is included so Pitfall-5's one-shot applier is a CI-caught presence property
    (its runtime correctness stays operator-only)."""
    services = _services()
    assert {"api", "worker", "gui", "postgres", "migrate"} <= services, (
        f"core services missing from bare config: {services}"
    )
    assert "litellm" not in services, (
        "a 'litellm' service is present — D-06 requires LiteLLM embedded in "
        "api/worker, not a standalone proxy container"
    )


def test_pgvector_image_present() -> None:
    """The mesh durable store pins the pgvector image (a vanilla postgres fails
    the CREATE EXTENSION vector in migration 0001)."""
    rendered = _compose_config()
    assert "pgvector/pgvector:pg16" in rendered, (
        "pgvector/pgvector:pg16 not found in the rendered config"
    )


def test_at_least_four_healthchecks_render() -> None:
    """At least four ``healthcheck:`` blocks render across the profiled stack
    (postgres, api, the model backend, and the Langfuse services). Pass every
    profile so all healthchecked services materialize."""
    rendered = _compose_config(
        "--profile", "vllm", "--profile", "langfuse", "--profile", "cpu"
    )
    assert rendered.count("healthcheck:") >= 4, (
        f"expected >= 4 healthcheck blocks, found {rendered.count('healthcheck:')}"
    )


def test_profiled_services_are_gated() -> None:
    """``vllm`` and ``langfuse-web`` appear ONLY when their profiles are named;
    they are ABSENT from the bare (no-profile) service set (L2 profile-gating)."""
    bare = _services()
    assert "vllm" not in bare, "vllm leaked into the bare (no-profile) service set"
    assert "langfuse-web" not in bare, (
        "langfuse-web leaked into the bare (no-profile) service set"
    )

    profiled = _services("--profile", "vllm", "--profile", "langfuse")
    assert "vllm" in profiled, "vllm absent under --profile vllm"
    assert "langfuse-web" in profiled, "langfuse-web absent under --profile langfuse"


def test_finding_gap_fixes_present_as_static_properties() -> None:
    """Cheap presence wins (NOT correctness): the two load-bearing functional
    gaps a static config cannot fully validate are at least DECLARED — the
    Finding #1 model-profile mount target and the Finding #2 docker-socket bind.
    Turns the gap-fixes into CI-caught presence properties (Pitfall 3 keeps the
    deeper correctness operator-only)."""
    rendered = _compose_config()
    assert "model_gateway.config.yaml" in rendered, (
        "Finding #1 model-profile mount target absent from the rendered config"
    )
    assert "/var/run/docker.sock" in rendered, (
        "Finding #2 docker-socket (DooD) bind absent from the rendered config"
    )
