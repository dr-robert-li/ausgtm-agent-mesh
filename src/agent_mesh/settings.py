"""Runtime settings sourced from environment variables.

No real secrets live here. Secret *names* map to Secret Manager entries wired in
at deploy time via ``--set-secrets`` (see scripts/gcp_deploy_core.sh). For local
dev, copy ``.env.example`` and export the values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # Deployment identity
    tenant_id: str = field(default_factory=lambda: os.getenv("TENANT_ID", "tenant-example"))
    client_slug: str = field(default_factory=lambda: os.getenv("CLIENT_SLUG", "example-client"))
    region: str = field(default_factory=lambda: os.getenv("REGION", "australia-southeast1"))
    project_id: str = field(default_factory=lambda: os.getenv("PROJECT_ID", ""))

    # Persistence: when DATABASE_URL is unset we fall back to the in-memory
    # repository so the POC is importable and testable without a database.
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    # Dispatch: when PUBSUB is disabled we use the in-process dispatcher so a
    # single host can run ingress + worker for local smoke checks.
    use_pubsub: bool = field(default_factory=lambda: _bool("USE_PUBSUB", False))
    task_topic: str = field(default_factory=lambda: os.getenv("TASK_TOPIC", "agent-mesh-tasks"))
    approval_topic: str = field(
        default_factory=lambda: os.getenv("APPROVAL_TOPIC", "agent-mesh-approvals")
    )
    dlq_topic: str = field(default_factory=lambda: os.getenv("DLQ_TOPIC", "agent-mesh-dlq"))

    # Model gateway. LiteLLM is the control plane; it routes upstream through the
    # Cloudflare AI Gateway wrapper. Agents/workers never call providers directly.
    litellm_base_url: str = field(
        default_factory=lambda: os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
    )
    model_route_profile: str = field(
        default_factory=lambda: os.getenv("MODEL_ROUTE_PROFILE", "mixed-cascade")
    )
    model_monthly_budget_usd: float = field(
        default_factory=lambda: float(os.getenv("MODEL_MONTHLY_BUDGET_USD", "50"))
    )

    # Slack signature verification window (seconds).
    slack_signing_secret_env: str = "SLACK_SIGNING_SECRET"
    slack_timestamp_tolerance_s: int = 60 * 5

    entrypoint: str = field(default_factory=lambda: os.getenv("ENTRYPOINT", "api"))


def get_settings() -> Settings:
    return Settings()
