"""Credential-docs completeness guard (04-09, D-12, TOOL-01/TOOL-04) — DEFAULT LANE.

This test proves the credential index (`docs/credentials/README.md`) is a *complete*,
drift-resistant D-12 deliverable: every env var the adapters' live lane actually reads
is documented, every per-provider setup doc exists, and the index links all four.

Drift resistance (threat T-04-09-02): instead of hardcoding the env var set, we DERIVE
it from the source of truth — the four live-test files (each gates on its provider's
creds via ``os.getenv("VAR")``) UNIONED with any ``os.getenv`` reads in the adapter
source. If a future adapter/live-test adds an env var, this guard fails until the index
documents it.

Creds-free + import-free: every file is read as TEXT (open + regex). We never import the
adapter or live-test modules (that could trigger optional-SDK imports in the default
lane) and never call ``os.getenv`` for a real secret. Repo-file reads only — so this
runs in the default ``pytest -m "not live"`` lane and stays green and creds-free.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_TESTS = _REPO / "tests"
_ADAPTERS = _REPO / "src" / "agent_mesh" / "tools" / "adapters"
_CRED_DOCS = _REPO / "docs" / "credentials"
_INDEX = _CRED_DOCS / "README.md"

# The four live-test files are the authoritative enumeration of the in-scope live-lane
# providers (deriving from the manifest's credential_secret_name would also pull in
# out-of-scope providers — Xero/Webflow/Bitscale/Cal.com/Clockify/Beehiiv — that have no
# adapter or doc this phase). We scan these PLUS the adapter source for completeness.
_LIVE_TEST_FILES = [
    "test_hubspot_live.py",
    "test_gws_live.py",
    "test_composio_live.py",
    "test_nango_live.py",
]

# The four per-provider setup docs the index must link + summarize (one per live lane).
_PROVIDER_DOCS = ["hubspot.md", "google_workspace.md", "composio.md", "nango.md"]

# Floor / anchors: the credential-proper env var that keys each provider's resolver.
# The derived set must be non-empty, meet this floor, and contain every anchor — so an
# empty/incomplete dynamic scan can never pass vacuously.
_ANCHOR_ENV_VARS = {
    "HUBSPOT_PRIVATE_APP_TOKEN",
    "GOOGLE_WORKSPACE_OAUTH",
    "COMPOSIO_API_KEY",
    "NANGO_SECRET_KEY",
}
_MIN_ENV_VARS = 7  # the seven live-lane env vars in scope this phase

# In the live-test files (the authoritative enumeration), provider creds appear as
# all-caps, underscore-bearing string literals — both directly (`os.getenv("VAR")`) and
# collected into tuples like Nango's ``_REQUIRED_ENV`` then read via ``os.getenv(v)``.
# Matching the literal SHAPE (not just direct os.getenv calls) catches the tuple form.
# In these files this pattern yields exactly the seven in-scope vars with no false
# positives (verified 04-09); if a future literal needs excluding, add it to _NON_ENV.
_ENV_LITERAL_RE = re.compile(r"""["']([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)["']""")
# Matches os.getenv("VAR") / os.environ["VAR"] / os.environ.get("VAR") in adapter source.
_ENV_READ_RE = re.compile(
    r"""os\.(?:getenv|environ(?:\.get)?)\s*[(\[]\s*["']([A-Z][A-Z0-9_]+)["']"""
)
# Guard against future false positives from the shape-based scan of the live-test files.
_NON_ENV: set[str] = set()


def _derive_live_lane_env_vars() -> set[str]:
    """Derive the live-lane env var set from the live-test files + adapter source (text).

    Live-test files: shape-scan for all-caps underscore literals (covers both direct
    ``os.getenv("VAR")`` and tuple-collected forms like Nango's ``_REQUIRED_ENV``).
    Adapter source: ``os.getenv``/``os.environ`` reads (future-proofs a direct adapter
    read added without a live test).
    """
    found: set[str] = set()
    for name in _LIVE_TEST_FILES:
        path = _TESTS / name
        if path.exists():
            found.update(_ENV_LITERAL_RE.findall(path.read_text(encoding="utf-8")))
    for path in sorted(_ADAPTERS.glob("*.py")):
        found.update(_ENV_READ_RE.findall(path.read_text(encoding="utf-8")))
    return found - _NON_ENV


def test_derived_env_var_set_is_complete_and_non_vacuous():
    """The dynamic scan must yield a non-empty set that meets the floor and all anchors —
    so the completeness assertion below can never pass against an empty/partial scan."""
    derived = _derive_live_lane_env_vars()
    assert derived, "derived live-lane env var set is empty — the scan regex/sources drifted"
    missing_anchors = _ANCHOR_ENV_VARS - derived
    assert not missing_anchors, (
        f"derived set is missing anchor env vars {sorted(missing_anchors)} — "
        "the live-test/adapter scan no longer covers every provider's credential"
    )
    assert len(derived) >= _MIN_ENV_VARS, (
        f"derived set {sorted(derived)} is below the {_MIN_ENV_VARS}-var floor — "
        "a live-lane env var was dropped from the live tests/adapters"
    )


def test_every_live_lane_env_var_is_documented_in_the_index():
    """Drift guard: every env var the live lane reads MUST appear in the credential index."""
    assert _INDEX.exists(), f"missing credential index: {_INDEX}"
    index_text = _INDEX.read_text(encoding="utf-8")
    undocumented = sorted(v for v in _derive_live_lane_env_vars() if v not in index_text)
    assert not undocumented, (
        f"live-lane env var(s) {undocumented} are read by the adapters/live tests but are "
        f"NOT documented in docs/credentials/README.md — D-12 would silently drift"
    )


def test_index_links_all_four_per_provider_docs():
    """The index ties the four per-provider docs together (D-12 deliverable)."""
    index_text = _INDEX.read_text(encoding="utf-8")
    missing = [doc for doc in _PROVIDER_DOCS if doc not in index_text]
    assert not missing, f"credential index does not link per-provider doc(s): {missing}"


def test_all_four_per_provider_docs_exist_and_are_non_empty():
    """Each per-provider setup doc must exist on disk and carry real content."""
    for doc in _PROVIDER_DOCS:
        path = _CRED_DOCS / doc
        assert path.exists(), f"missing per-provider credential doc: {path}"
        assert path.read_text(encoding="utf-8").strip(), f"per-provider doc is empty: {path}"


def test_index_documents_the_per_provider_opt_in_skip_matrix():
    """D-11: the index records that each provider is independently skippable on its creds."""
    index_text = _INDEX.read_text(encoding="utf-8").lower()
    assert "skip" in index_text, "index must document per-provider live-test skip behaviour"
    assert "opt-in" in index_text or "opt in" in index_text, (
        "index must document the per-provider opt-in live-lane matrix (D-11)"
    )
