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

    # Model gateway. A LiteLLM-compatible gateway is the model control plane
    # (routing/cascades/budgets/token caps/provider abstraction); it can route
    # upstream through the Cloudflare AI Gateway wrapper. Agents/workers never
    # call providers directly. Both Anthropic-direct and Vertex AI paths are
    # first class — selected per route, not per code path.
    model_gateway_base_url: str = field(
        default_factory=lambda: os.getenv(
            "MODEL_GATEWAY_BASE_URL", os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
        )
    )
    # "anthropic" | "vertex_ai" | "mixed" — informational default provider posture.
    model_provider_mode: str = field(
        default_factory=lambda: os.getenv("MODEL_PROVIDER_MODE", "mixed")
    )
    model_route_profile: str = field(
        default_factory=lambda: os.getenv("MODEL_ROUTE_PROFILE", "mixed-cascade")
    )
    model_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("MODEL_MAX_TOKENS", "4096"))
    )
    model_monthly_budget_usd: float = field(
        default_factory=lambda: float(os.getenv("MODEL_MONTHLY_BUDGET_USD", "50"))
    )
    # Per-task hard cap. Defaults to the per-user monthly cap (so a single task can,
    # by default, spend up to the whole monthly budget) but can be tightened per
    # deployment via MODEL_PER_TASK_CAP. The budget ledger enforces
    # min(per-user remaining, per-task remaining) before each call (D-05).
    model_per_task_cap: float = field(
        default_factory=lambda: float(
            os.getenv("MODEL_PER_TASK_CAP", os.getenv("MODEL_MONTHLY_BUDGET_USD", "50"))
        )
    )

    # Cloudflare AI Gateway model-traffic governance plane (integration-ready;
    # wired by 03-02). When cf_enabled is True, the LiteLLM Router routes upstream
    # through cf_aig_wrapper_url. Inert here; shared scaffolding for wave-2 plans.
    cf_enabled: bool = field(default_factory=lambda: _bool("CF_ENABLED", False))
    cf_aig_wrapper_url: str = field(
        default_factory=lambda: os.getenv("CF_AIG_WRAPPER_URL", "")
    )

    # OpenTelemetry OTLP/HTTP exporter endpoint for Langfuse trace ingestion
    # (consumed by 03-03). Empty disables the exporter (default-suite-safe).
    otel_exporter_otlp_endpoint: str = field(
        default_factory=lambda: os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    )

    # Langfuse observability (default required platform for this variant).
    langfuse_public_key: str = field(
        default_factory=lambda: os.getenv("LANGFUSE_PUBLIC_KEY", "")
    )
    langfuse_secret_key: str = field(
        default_factory=lambda: os.getenv("LANGFUSE_SECRET_KEY", "")
    )
    langfuse_host: str = field(
        default_factory=lambda: os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    )

    # Slack signature verification window (seconds).
    slack_signing_secret_env: str = "SLACK_SIGNING_SECRET"
    slack_timestamp_tolerance_s: int = 60 * 5

    # Approval-token signing secret. UNLIKE Slack (which fails open in dev), the
    # approval gate FAILS CLOSED when this secret is unset — see
    # approvals.verify_approval_token. The name maps to a Secret Manager entry
    # wired at deploy time.
    approval_signing_secret_env: str = "APPROVAL_SIGNING_SECRET"

    entrypoint: str = field(default_factory=lambda: os.getenv("ENTRYPOINT", "api"))


def get_settings() -> Settings:
    return Settings()
