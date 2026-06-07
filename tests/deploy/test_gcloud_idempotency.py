"""DEP-01: prove the gcloud/wrangler deploy scripts are deploy-ready *locally*.

This harness proves three things WITHOUT ever reaching a real cloud:

1. **Reuse-vs-create idempotency LOGIC (D-09).** A CATCH-ALL fake ``gcloud`` /
   ``wrangler`` (``tests/deploy/bin/``) is shadowed onto ``PATH`` *only inside*
   ``subprocess.run(env=...)``. It records every argv and, by default, exits 0
   ("resource exists" → reuse). A per-test ``SHIM_ABSENT_PATTERN`` makes ONE
   specific ``describe`` probe report non-0 ("absent"), so the corresponding
   ``describe ... || create`` branch fires. We assert BOTH directions for
   multiple resource branches:
     - EXISTS  → ``create`` is NEVER recorded (short-circuit / reuse)
     - ABSENT  → ``create`` IS recorded
   The fake binary is the only record of any gcloud/wrangler invocation, so no
   real cloud call can happen (T-07-10 / T-07-11 mitigations: catch-all shim +
   subprocess-scoped prepended PATH).

2. **An always-on ``bash -n`` syntax floor (D-10 / DEP-01 "syntax check").**
   This is the real, NON-skip-gated proof the scripts parse. It runs wherever
   ``bash`` exists.

3. **A ``shellcheck`` lint leg that SKIPS LOUDLY when the tool is absent
   (D-10 / SP-5 anti-silent-cap).** No silent gap: the skip names the tool and
   what was skipped.

Also asserted here as deploy-config consistency (NOT a fault harness): the
Pub/Sub worker subscription declares ``--dead-letter-topic`` and
``--max-delivery-attempts=5``. That is the literal "job retry" (redelivery) leg
of E2E-03, completed as deploy-config evidence per plan 07-03 (the milestone does
no live provisioning, so the redelivery wiring is proven by config, not a run).

No ``live`` marker: the whole module runs in the default ``-m "not live"`` lane.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

# tests/deploy/<this file>  ->  parents[2] == repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_SHIM_DIR = Path(__file__).resolve().parent / "bin"

_BOOTSTRAP = _SCRIPTS_DIR / "gcp_bootstrap.sh"
_DEPLOY_CORE = _SCRIPTS_DIR / "gcp_deploy_core.sh"
_CF_DEPLOY = _SCRIPTS_DIR / "cf_deploy_ai_gateway_worker.sh"

# Minimal env contract so each script gets past its ``: "${VAR:?}"`` guards.
# PROJECT_ID and CLOUDFLARE_ACCOUNT_ID are the only ``:?`` (required) vars; the
# rest take ``:=`` defaults but we pin them for determinism.
_BASE_ENV = {
    "PROJECT_ID": "fake-project",
    "REGION": "australia-southeast1",
    "CREATE_PROJECT": "false",
    "AR_REPO": "agent-mesh",
    "SQL_INSTANCE": "agent-mesh-poc",
    "SQL_DATABASE": "agent_mesh",
    "TENANT_ID": "tenant-example",
    "CLIENT_SLUG": "example-client",
    "MODEL_ROUTE_PROFILE": "mixed-cascade",
    "IMAGE_TAG": "latest",
    "CLOUDFLARE_ACCOUNT_ID": "fake-cf-account",
    "CLOUDFLARE_AI_GATEWAY_ID": "agent-mesh-poc",
    "WRANGLER_ENV": "poc",
    "REUSE_EXISTING_CLOUDFLARE_GATEWAY": "true",
}


def _run_script(
    script: Path,
    tmp_path: Path,
    *,
    absent_pattern: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> list[str]:
    """Run ``script`` under the shimmed PATH and return the recorded argv lines.

    The shim dir is PREPENDED to PATH (so the fake binary wins over any real
    gcloud/wrangler — T-07-11) and that override lives ONLY in this subprocess's
    env, never the session PATH. ``cwd=_REPO_ROOT`` because cf_deploy does a
    ``cd cloudflare/...`` relative to the repo root.
    """
    shim_log = tmp_path / "shim.log"
    env = dict(os.environ)
    env["PATH"] = str(_SHIM_DIR) + os.pathsep + env.get("PATH", "")
    env["SHIM_LOG"] = str(shim_log)
    if absent_pattern is not None:
        env["SHIM_ABSENT_PATTERN"] = absent_pattern
    env.update(_BASE_ENV)
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        ["bash", str(script)],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"{script.name} exited {result.returncode} under the shim.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    if not shim_log.exists():
        return []
    return [line for line in shim_log.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Always-on syntax floor (NOT skip-gated) — the real DEP-01 "syntax check".
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("script", sorted(_SCRIPTS_DIR.glob("*.sh")), ids=lambda p: p.name)
def test_bash_n_syntax_floor(script: Path) -> None:
    """``bash -n`` over every scripts/*.sh — always runs wherever bash exists.

    This is the non-skip-gated floor: a syntax regression in any deploy script
    FAILS here (it is never skipped), so the default lane always proves something
    real about the scripts.
    """
    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"bash -n failed for {script.name}:\n{result.stderr}"


# ---------------------------------------------------------------------------
# shellcheck lint leg — LOUD skip when absent (D-10 / SP-5).
# ---------------------------------------------------------------------------


def test_shellcheck_lint_loud_skip() -> None:
    """Run ``shellcheck scripts/*.sh`` when installed, else SKIP LOUDLY.

    Empirically shellcheck is absent on this dev machine, so this is the actual
    default-lane path — and the skip NAMES the gap (never a silent cap).
    """
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not installed; gcloud/wrangler-script lint skipped")
    scripts = sorted(str(p) for p in _SCRIPTS_DIR.glob("*.sh"))
    result = subprocess.run(
        ["shellcheck", *scripts],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"shellcheck found issues:\n{result.stdout}\n{result.stderr}"


# ---------------------------------------------------------------------------
# Reuse-vs-create idempotency logic (D-09) — both directions, multiple branches.
# ---------------------------------------------------------------------------


def test_artifact_registry_reuse_when_exists(tmp_path: Path) -> None:
    """EXISTS lane: when ``artifacts repositories describe`` returns 0 (reuse),
    ``artifacts repositories create`` is NEVER recorded (the ``|| create`` short-
    circuits)."""
    calls = _run_script(_BOOTSTRAP, tmp_path)  # no absent pattern => all exist
    assert any("artifacts repositories describe" in c for c in calls)
    assert not any("artifacts repositories create" in c for c in calls), (
        "create must NOT run when the repository already exists"
    )


def test_artifact_registry_create_when_absent(tmp_path: Path) -> None:
    """ABSENT lane: when only the AR describe probe reports non-0, the
    ``artifacts repositories create`` branch fires (and nothing else aborts)."""
    calls = _run_script(
        _BOOTSTRAP, tmp_path, absent_pattern=r"artifacts repositories describe"
    )
    assert any("artifacts repositories describe" in c for c in calls)
    assert any("artifacts repositories create" in c for c in calls), (
        "create MUST run when the repository is absent"
    )


def test_pubsub_subscription_reuse_when_exists(tmp_path: Path) -> None:
    """EXISTS lane for the worker subscription: describe succeeds → no create."""
    calls = _run_script(_BOOTSTRAP, tmp_path)
    assert any("pubsub subscriptions describe agent-mesh-tasks-worker" in c for c in calls)
    assert not any(
        "pubsub subscriptions create agent-mesh-tasks-worker" in c for c in calls
    ), "subscription create must NOT run when it already exists"


def test_pubsub_subscription_create_when_absent(tmp_path: Path) -> None:
    """ABSENT lane: the worker-subscription describe reports non-0 → create fires."""
    calls = _run_script(
        _BOOTSTRAP,
        tmp_path,
        absent_pattern=r"pubsub subscriptions describe agent-mesh-tasks-worker",
    )
    assert any(
        "pubsub subscriptions create agent-mesh-tasks-worker" in c for c in calls
    ), "subscription create MUST run when absent"


def test_service_account_reuse_when_exists(tmp_path: Path) -> None:
    """EXISTS lane: SA describe succeeds → no ``iam service-accounts create``."""
    calls = _run_script(_BOOTSTRAP, tmp_path)
    assert any("iam service-accounts describe" in c for c in calls)
    assert not any("iam service-accounts create" in c for c in calls), (
        "service-account create must NOT run when the SA already exists"
    )


def test_cloud_sql_instance_create_when_absent(tmp_path: Path) -> None:
    """ABSENT lane: the Cloud SQL instance describe reports non-0 → instance
    create fires (the ``if ! gcloud sql instances describe`` guard)."""
    calls = _run_script(
        _BOOTSTRAP, tmp_path, absent_pattern=r"sql instances describe"
    )
    assert any("sql instances create agent-mesh-poc" in c for c in calls), (
        "Cloud SQL instance create MUST run when the instance is absent"
    )


def test_deploy_job_update_when_exists(tmp_path: Path) -> None:
    """EXISTS lane for deploy_core: ``run jobs describe`` succeeds → action=update
    (``run jobs update``), NOT create."""
    calls = _run_script(_DEPLOY_CORE, tmp_path)
    assert any("run jobs describe agent-mesh-worker" in c for c in calls)
    assert any("run jobs update agent-mesh-worker" in c for c in calls), (
        "deploy_job must UPDATE an existing job"
    )
    assert not any("run jobs create agent-mesh-worker" in c for c in calls), (
        "deploy_job must NOT create when the job already exists"
    )


def test_deploy_job_create_when_absent(tmp_path: Path) -> None:
    """ABSENT lane for deploy_core: ``run jobs describe`` reports non-0 →
    action=create (``run jobs create``)."""
    calls = _run_script(
        _DEPLOY_CORE, tmp_path, absent_pattern=r"run jobs describe agent-mesh-worker"
    )
    assert any("run jobs create agent-mesh-worker" in c for c in calls), (
        "deploy_job must CREATE when the job is absent"
    )
    assert not any("run jobs update agent-mesh-worker" in c for c in calls), (
        "deploy_job must NOT update a job that does not exist"
    )


def test_cf_wrangler_deploy_runs_under_shim(tmp_path: Path) -> None:
    """The Cloudflare wrapper script drives ``wrangler whoami`` + ``wrangler
    deploy --env poc`` through the fake wrangler shim — no real Cloudflare call.

    This also proves the PATH override is subprocess-scoped: the fake wrangler is
    the only thing that could have recorded these argv lines.
    """
    calls = _run_script(_CF_DEPLOY, tmp_path)
    assert any("whoami" in c for c in calls)
    assert any("deploy --env poc" in c for c in calls)


# ---------------------------------------------------------------------------
# Pub/Sub redelivery (E2E-03 "job retry") asserted as deploy-config consistency.
# Cross-ref plan 07-03: the milestone does no live provisioning, so the worker
# subscription's dead-letter + max-delivery-attempts wiring is proven by config.
# ---------------------------------------------------------------------------


def test_pubsub_redelivery_config_present() -> None:
    """gcp_bootstrap.sh declares ``--dead-letter-topic`` and
    ``--max-delivery-attempts=5`` on the worker subscription — the literal
    Pub/Sub job-retry (redelivery) evidence for E2E-03 (cross-ref plan 07-03)."""
    text = _BOOTSTRAP.read_text()
    assert "--dead-letter-topic" in text, "worker subscription must wire a dead-letter topic"
    assert "--max-delivery-attempts=5" in text, (
        "worker subscription must set max-delivery-attempts=5 (E2E-03 job-retry config)"
    )
