# Spike Manifest

## Idea
Decide whether Composio.dev should be added to the agent-mesh roadmap as a
fallback/alternative to Nango for the project's *generic MCP aggregator* tool-gateway
integration style — and validate the underlying "Composio has better coverage" claim
with evidence before committing it to the roadmap.

## Requirements
Design decisions emerging from spiking. Updated as spikes progress.

- Coverage claims about aggregators MUST name the counting unit (providers/apps vs
  toolkits vs tools) — they are not interchangeable (Spike 001).
- The generic MCP-aggregator slot is evaluated on **MCP-nativeness**, not only raw
  connector count (Spike 001).
- Prefer independently verifiable (open-source) catalogs where the count matters;
  flag publisher-stated figures as such (Spike 001).

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | composio-vs-nango-coverage | comparison | Composio vs Nango coverage + fitness for the generic MCP-aggregator slot | ✓ VALIDATED (nuanced) | tooling, mcp, aggregator, nango, composio, coverage, roadmap |
