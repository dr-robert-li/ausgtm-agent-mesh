---
spike: 001
name: composio-vs-nango-coverage
type: comparison
validates: "Given the project's generic MCP-aggregator slot (currently nango_aggregator), when Composio.dev is compared on coverage and MCP-nativeness, then we can decide whether Composio is a justified fallback/alternative aggregator integration style for the roadmap"
verdict: VALIDATED
related: []
tags: [tooling, mcp, aggregator, nango, composio, coverage, roadmap]
---

# Spike 001: Composio.dev vs Nango — generic MCP aggregator coverage

## What This Validates
Given the project's tool-gateway integration styles (`direct_api`, `mcp_server`,
`aggregate_mcp`, `nango_aggregator` — see `CLAUDE.md` §"Tool Pack Contract" and
acceptance criterion 13; `REQUIREMENTS.md` TOOL-04), **when** Composio.dev is compared
against Nango on (a) raw connector coverage and (b) fitness for the *generic MCP
aggregator* role, **then** we can decide whether adding Composio as a
fallback/alternative aggregator integration style on the roadmap is justified — and on
what evidence, not vibes.

This is a **lightweight coverage spike** (chosen scope): no credentials, no live
tool-execution. It measures coverage from public/open sources and surfaces the
counting-unit nuance behind the "better coverage" claim.

## Research

| Dimension | Nango | Composio | Source |
|-----------|-------|----------|--------|
| Connector count (raw) | **838 providers** (live-counted from open-source `providers.yaml`) | **500+ apps / 982+ toolkits / 20,000+ tools** (publisher-stated; catalog is `x-api-key`-gated) | NangoHQ/nango repo; composio.dev/toolkits |
| Verifiability of count | High — open-source registry, anyone can count | Low — toolkit list requires API key; figure is marketing-stated | — |
| MCP model | Unified-API/auth first; **~20** MCP-capable providers today (`auth_mode: MCP_OAUTH2`, `-mcp` slugs) | **MCP-native**: single unified MCP endpoint ("Tool Router" GA 2026-05) fronting the whole catalog | providers.yaml; Composio Tool Router |
| Natural project slot | `nango_aggregator` (unified API + managed auth) | `aggregate_mcp` (single MCP endpoint → many apps) | CLAUDE.md Tool Pack Contract |
| Licensing / self-host | Open-source, self-hostable | Commercial SaaS ($29M funded, ~28k GH stars) | search 2026-06 |

**Chosen approach:** count Nango live from the authoritative open-source registry
(`packages/providers/providers.yaml`); for Composio, record the publisher figure and
**explicitly flag** that no no-auth count exists — do not fabricate a counted number.
The asymmetry (open vs auth-gated catalog) is itself a finding.

**Gotcha:** "coverage" has no single unit. Nango counts *providers/APIs*; Composio
counts *apps*, *toolkits*, and *tools* — three different denominators. A bare
"X has more integrations" claim is unsound without naming the unit.

## How to Run
```bash
python3 .planning/spikes/001-composio-vs-nango-coverage/compare_coverage.py
# offline (recorded figures only, no network):
python3 .planning/spikes/001-composio-vs-nango-coverage/compare_coverage.py --offline
```
Stdlib only (urllib + re) — matches the project's no-extra-deps ethos.

## What to Expect
A live count of Nango providers (~838 as of 2026-06) and MCP-capable entries (~20),
the published Composio figures with the auth-gated caveat, and a verdict-inputs block.

## Investigation Trail
1. **Initial claim:** "Composio has better coverage than Nango." Searched both
   vendors' 2026 figures: Composio markets 500+ apps / 982+ toolkits / 20k+ tools;
   Nango markets 800+ APIs / 2000+ templates.
2. **Sought a verifiable count, not marketing.** Nango is open-source → counted
   top-level keys in `providers.yaml` directly: **838** (live). Composio's toolkit
   list is behind `x-api-key` (confirmed via docs API-reference) → no clean no-auth
   count; recorded the publisher figure and flagged it.
3. **Reframed against the actual slot.** The roadmap slot is a *generic MCP
   aggregator*. Re-counted Nango's MCP-capable providers: only ~20 today
   (`auth_mode: MCP_OAUTH2`). Composio exposes one unified MCP endpoint over its
   whole catalog (Tool Router, GA 2026-05).
4. **Surprise:** on RAW connectors the two are near parity (Nango 838 verifiable vs
   Composio 500–982 stated) — "better coverage" is *not* clearly true by app count.
   But for **MCP-native breadth** (single endpoint over 982 toolkits / 20k tools),
   Composio is materially ahead. The claim is unit-dependent.

## Results
**Verdict: VALIDATED (with nuance) — Composio is a justified alternative/fallback
MCP-aggregator integration style, but the rationale is MCP-nativeness, not a clean
raw-count win.**

Evidence:
- **Raw connector coverage ≈ parity.** Nango **838** (independently counted) vs
  Composio **500+ apps / 982 toolkits** (stated). No decisive raw-count advantage
  either way; the headline "better coverage" is true only when counting
  toolkits/tools, not apps/providers.
- **MCP-aggregator fitness → Composio.** Single unified MCP endpoint (Tool Router)
  over the full catalog vs Nango's ~20 MCP-capable providers. For the *generic MCP
  aggregator* role specifically, Composio is the stronger fit.
- **Trade-off → Nango.** Open-source, self-hostable, independently verifiable
  catalog, managed auth. Composio is commercial SaaS with an auth-gated catalog.
- **Architecture fit:** Composio maps cleanly onto the existing `aggregate_mcp`
  style (single MCP endpoint); it does not require a brand-new style — though a
  named `composio_aggregator` style parallel to `nango_aggregator` is the more
  explicit option.

**Recommendation for the roadmap/requirements (proposal — not yet applied):**
Add Composio.dev as an alternative/fallback generic MCP aggregator alongside
`nango_aggregator`. Two framings; the spike favors keeping both as peer options
rather than a strict hierarchy:
- Nango = open-source unified-API aggregator (auth + 838 APIs, self-hostable).
- Composio = MCP-native aggregator (single Tool Router endpoint, 982 toolkits / 20k
  tools) for when MCP breadth / single-endpoint routing matters more than self-host.

Suggested edits: `REQUIREMENTS.md` TOOL-04 to name Composio as a peer aggregator;
`CLAUDE.md` Tool Pack Contract integration-style list + acceptance criterion 13 to
add a Composio aggregator style; map to whichever roadmap phase owns the Tool
Gateway / aggregator work (TOOL-0x).

**Limitations:** coverage measured from public sources only; no live tool-execution
or auth-flow comparison (that would be the *Full integration spike* — needs keys).
Composio count is publisher-stated, not independently verified.
