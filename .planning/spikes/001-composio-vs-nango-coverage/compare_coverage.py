#!/usr/bin/env python3
"""Spike 001 — Composio vs Nango as generic MCP aggregator: coverage comparison.

Observable question: does Composio.dev actually have *better coverage* than Nango,
and which is the more natural fit for the project's `aggregate_mcp` / `nango_aggregator`
integration-style slot?

Design constraints (match project ethos: stdlib only, no extra deps, no secrets):
- Nango: count is computed LIVE from the open-source provider registry (no auth).
- Composio: the toolkit list sits behind `x-api-key`, so there is no clean
  unauthenticated count. We record the published figures and FLAG the asymmetry
  rather than pretend to a number we cannot verify.

Run:
    python3 compare_coverage.py            # live fetch (needs network)
    python3 compare_coverage.py --offline  # use recorded figures only
"""
from __future__ import annotations

import re
import sys
import urllib.request

NANGO_PROVIDERS_YAML = (
    "https://raw.githubusercontent.com/NangoHQ/nango/master/"
    "packages/providers/providers.yaml"
)

# Published figures (sourced 2026-06; see README Research section). Used as the
# Composio side (no public no-auth count) and as the offline fallback for Nango.
PUBLISHED = {
    "nango": {"apis": "800+", "templates": "2000+", "source": "nango.dev/api-integrations"},
    "composio": {
        "apps": "500+",
        "toolkits": "982+",
        "tools": "20000+",
        "source": "composio.dev/toolkits",
    },
}


def fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "spike-001/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted host)
        return resp.read().decode("utf-8", "replace")


def count_nango_providers(yaml_text: str) -> tuple[int, int]:
    """Count top-level provider keys and how many advertise MCP.

    providers.yaml keys each provider at column 0 as `slug:`. We avoid a YAML dep
    by counting column-0 keys that are not comment/anchor lines.
    """
    providers = re.findall(r"(?m)^([a-z0-9][a-z0-9._-]*):\s*$", yaml_text)
    total = len(providers)
    # MCP-capable providers advertise an MCP auth mode or an `-mcp` slug.
    mcp = len(re.findall(r"(?mi)^\s*auth_mode:\s*MCP", yaml_text))
    mcp_slugs = len([p for p in providers if p.endswith("-mcp") or "-mcp-" in p])
    return total, max(mcp, mcp_slugs)


def main() -> int:
    offline = "--offline" in sys.argv
    print("=" * 64)
    print("SPIKE 001 — Composio vs Nango coverage (MCP aggregator slot)")
    print("=" * 64)

    nango_total = None
    nango_mcp = None
    if not offline:
        try:
            yaml_text = fetch(NANGO_PROVIDERS_YAML)
            nango_total, nango_mcp = count_nango_providers(yaml_text)
            print(f"\n[LIVE] Nango open-source providers.yaml:")
            print(f"  providers (top-level keys) : {nango_total}")
            print(f"  MCP-capable providers       : {nango_mcp}")
            print(f"  source: {NANGO_PROVIDERS_YAML}")
        except Exception as exc:  # network blocked / offline
            print(f"\n[WARN] live Nango fetch failed ({exc!r}); using published figure")

    if nango_total is None:
        print(f"\n[PUBLISHED] Nango: {PUBLISHED['nango']['apis']} APIs, "
              f"{PUBLISHED['nango']['templates']} templates "
              f"({PUBLISHED['nango']['source']})")

    print(f"\n[PUBLISHED] Composio: {PUBLISHED['composio']['apps']} apps, "
          f"{PUBLISHED['composio']['toolkits']} toolkits, "
          f"{PUBLISHED['composio']['tools']} tools "
          f"({PUBLISHED['composio']['source']})")
    print("  NOTE: Composio toolkit list requires x-api-key — no no-auth count. "
          "Figure is publisher-stated, not independently counted by this spike.")

    print("\n" + "-" * 64)
    print("VERDICT INPUTS")
    print("-" * 64)
    live = f"{nango_total} (live-counted)" if nango_total else f"{PUBLISHED['nango']['apis']} (published)"
    print(f"  Nango coverage     : {live}  — open-source, independently verifiable")
    print(f"  Composio coverage  : {PUBLISHED['composio']['apps']}+ apps / "
          f"{PUBLISHED['composio']['toolkits']} toolkits — larger, MCP-native, "
          f"but auth-gated catalog")
    print("  MCP-native single endpoint: Composio YES (Tool Router GA 2026-05); "
          "Nango PARTIAL (per-provider MCP_OAUTH2 entries, unified-API first)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
