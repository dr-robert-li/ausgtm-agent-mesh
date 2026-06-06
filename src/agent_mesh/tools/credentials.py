"""Credential resolution for the Tool Gateway (D-02).

A small abstraction keyed by the manifest's ``credential_secret_name``. The local
backend (:class:`EnvCredentialResolver`) reads ``os.environ[name]``; the prod
backend swaps to Google Secret Manager behind the same :class:`CredentialResolver`
Protocol — the engine never changes.

D-02 HARD RULE: a credential is resolved **only inside** ``ToolGateway.execute()``
and is **never** returned to the graph/agent, set as a span attribute, or logged.
The adapter receives the resolved value as a keyword argument at call time and the
engine discards it when ``execute()`` returns. When the secret is absent the
resolver returns ``None`` so the adapter degrades to the deterministic stub (D-11),
keeping ``make test`` green and creds-free.

Prod swap seam (NOT built this phase, documented for D-12):

    class SecretManagerResolver:
        def resolve(self, secret_name: str | None) -> str | None:
            # google-cloud-secret-manager access_secret_version(...).payload.data
            ...

For Google Workspace the single ``GOOGLE_WORKSPACE_OAUTH`` secret resolves to a
JSON blob ``{client_id, client_secret, refresh_token}`` (the unattended-refresh
material), not a single token — the adapter parses that blob.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class CredentialResolver(Protocol):
    """Resolve a manifest ``credential_secret_name`` to its secret value."""

    def resolve(self, secret_name: str | None) -> str | None: ...


class EnvCredentialResolver:
    """Local, creds-free-by-default resolver backed by environment variables.

    Returns ``None`` when ``secret_name`` is falsy or the variable is unset, so the
    adapter degrades to the deterministic stub (D-11).
    """

    def resolve(self, secret_name: str | None) -> str | None:
        if not secret_name:
            return None
        return os.getenv(secret_name)
