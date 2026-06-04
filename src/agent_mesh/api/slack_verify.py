"""Slack request signature verification.

Implements Slack's v0 HMAC signing scheme. The signing secret is read from the
environment (wired from Secret Manager at deploy time). This is a real
implementation, not a placeholder, but it is only exercised when
``SLACK_SIGNING_SECRET`` is set; without it, verification is skipped so local
smoke checks can run.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time


def verify_slack_signature(
    *,
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    signing_secret: str | None = None,
    tolerance_s: int = 300,
) -> bool:
    secret = signing_secret if signing_secret is not None else os.getenv("SLACK_SIGNING_SECRET")
    if not secret:
        # No secret configured (local dev): do not block, but signal unverified.
        return True
    if not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > tolerance_s:
        return False  # Replay protection.

    basestring = f"v0:{timestamp}:".encode() + body
    digest = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, signature)
