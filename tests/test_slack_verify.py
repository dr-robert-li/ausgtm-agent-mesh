import hashlib
import hmac
import time

from agent_mesh.api.slack_verify import verify_slack_signature


def _sign(secret: str, ts: str, body: bytes) -> str:
    base = f"v0:{ts}:".encode() + body
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    secret = "shhh"
    ts = str(int(time.time()))
    body = b'{"type":"event_callback"}'
    sig = _sign(secret, ts, body)
    assert verify_slack_signature(
        body=body, timestamp=ts, signature=sig, signing_secret=secret
    )


def test_tampered_body_rejected():
    secret = "shhh"
    ts = str(int(time.time()))
    sig = _sign(secret, ts, b"original")
    assert not verify_slack_signature(
        body=b"tampered", timestamp=ts, signature=sig, signing_secret=secret
    )


def test_stale_timestamp_rejected():
    secret = "shhh"
    ts = str(int(time.time()) - 10_000)
    body = b"x"
    sig = _sign(secret, ts, body)
    assert not verify_slack_signature(
        body=body, timestamp=ts, signature=sig, signing_secret=secret, tolerance_s=300
    )


def test_no_secret_skips_verification():
    # Local dev: no secret configured -> do not block.
    assert verify_slack_signature(body=b"x", timestamp=None, signature=None, signing_secret="")
