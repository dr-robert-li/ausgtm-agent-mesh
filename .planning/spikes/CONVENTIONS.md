# Spike Conventions

Patterns and stack choices established across spike sessions. New spikes follow these
unless the question requires otherwise.

## Stack
- **Language:** Python 3 (matches the project — `pyproject.toml`, `pythonpath=["src"]`).
- **Deps:** stdlib only for spikes where possible (`urllib`, `re`) — mirrors the
  project ethos that `make test` / `make smoke` run with no cloud/extra deps.

## Patterns
- **No secrets in spikes** (explicitly chosen, session 001). Measure from public /
  open-source sources; do not require API keys for a coverage/feasibility read.
- **Verifiable over stated.** Where a count matters, compute it from an open source
  and label any publisher-stated figure as unverified.
- **Name the unit.** Comparative claims (coverage, throughput, count) must state the
  denominator; reject bare "more than X" claims.
- **`--offline` flag** on network-touching spike scripts so they degrade to recorded
  figures when network is blocked.

## Structure
- One dir per spike: `.planning/spikes/NNN-descriptive-name/` with a runnable script
  + `README.md` (frontmatter, Research, Investigation Trail, Results).
