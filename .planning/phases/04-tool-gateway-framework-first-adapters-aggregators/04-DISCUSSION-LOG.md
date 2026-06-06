# Phase 4: Tool Gateway Framework + First Adapters + Aggregators - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-06
**Phase:** 04-tool-gateway-framework-first-adapters-aggregators
**Areas discussed:** Milestone re-scope, Direct adapter targets, Aggregator choice, Schema boundary, Google Workspace scope, Aggregator depth

---

## Gray-area selection (entry point)

The original Phase-4 framing (TOOL-01/02 + SI-01/02) presented 4 areas: Adapter target + creds,
Schema boundary, Eval harness, AI-BOM + promotion wiring. User selected **all 4** — but then
redirected before answering, asking for **full tool coverage** (all reference providers + aggregators)
and "treat POC as MVP — viable general functionality." This triggered a milestone re-scope rather than
a within-phase clarification.

---

## Milestone re-scope

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — breadth across phases, SI moves later | Re-roadmap; TOOL-03/04 → v1; framework+aggregator first, providers fan out; SI sequenced later | ✓ |
| Yes, but keep SI in the very next phase too | Same re-scope, pack framework+adapters+SI into next phase | |
| Not yet — show me the full re-roadmap first | Draft revised REQUIREMENTS+ROADMAP as a proposal before committing | |

**User's choice:** Yes — breadth across phases, SI moves later.
**Notes:** Drove promotion of TOOL-03 + TOOL-04 from v2→v1 and a 5→7 phase split. Ingress (Slack +
Claude/MCP) confirmed already built — not re-opened. GSD bookkeeping mechanism (in-place roadmap edit
vs new-milestone) decided by Claude per advisor guidance.

## Direct adapter targets (priority-1, multiSelect)

| Option | Description | Selected |
|--------|-------------|----------|
| HubSpot | Bearer token; read + write-gated; schemas exist | ✓ |
| Google Workspace | Gmail/Calendar/Drive/Sheets/Docs/Slides; OAuth; heaviest | ✓ |
| Xero | Financial; manifest routes via nango_aggregator | (not picked — stays aggregator) |
| Cal.com / Clockify | Lighter API-key providers | ✓ |
| Webflow | (added by user) | ✓ |
| Bitscale | (added by user) | ✓ |
| Beehiiv | (added by user) | ✓ |

**User's choice:** All providers except Xero as direct. **Interpreted + sequenced:** HubSpot + full
Google Workspace land **direct in Phase 4** (flagships); Cal.com, Clockify, Webflow, Bitscale, Beehiiv
fan to **Phase 5** breadth; Xero via aggregator in Phase 5.

## Aggregator choice

| Option | Description | Selected |
|--------|-------------|----------|
| Composio primary + Nango fallback | Spike 001 winner, MCP-native; Nango OSS fallback | ✓ |
| Nango primary + Composio fallback | Lead with OSS self-hosted | |
| Both equal, first-class | Neither primary | |

**User's choice:** Composio primary + Nango fallback.

## Schema boundary (TOOL-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Fail-closed (no schema = blocked) | Every direct adapter must ship a schema | ✓ |
| Warn + pass-through | Missing schema logs warning, executes | |
| Fail-closed for write-class only | Strict on writes, lenient reads | |

**User's choice:** Fail-closed (no schema = blocked) — for **direct** tools.
**Notes:** User challenged whether mandatory schemas make the gate too narrow. Resolved into a richer
model (CONTEXT D-04/05/06): validation strictness is an authoring choice (permissive by default,
allow extras); aggregate tools validate against **runtime** aggregator-supplied schemas (never
fail-closed on a missing manifest schema); input violation = hard reject (no call), output violation =
flag/quarantine (call already happened). Fail-closed applies to **direct tools only**.

## Google Workspace scope

| Option | Description | Selected |
|--------|-------------|----------|
| Drive search (read) | Cleanest OAuth-read proof | (subsumed) |
| Gmail send | Approval-gated write path | (subsumed) |
| Sheets append | Approval-gated write | (subsumed) |
| Calendar / Docs / Slides — defer | Push to Phase 5 | |
| **Full suite (Drive, Gmail, Calendar, Docs, Slides, Sheets)** | Prove path AND all of Workspace | ✓ |

**User's choice:** Full Google Workspace suite live in Phase 4.
**Notes:** Implies authoring ~6 products of new manifest entries + schemas (only Drive has one today) —
flagged in CONTEXT D-08 for the planner.

## Aggregator depth (TOOL-04)

| Option | Description | Selected |
|--------|-------------|----------|
| One real read per aggregator | Composio managed + Nango self-hosted, one read each | ✓ |
| Composio live, Nango contract-only | Composio live, Nango structural/mocked | |
| Both live + a write through aggregator | Most ambitious; gated write via aggregate path | |

**User's choice:** One real read per aggregator (Composio managed auth + Nango self-hosted).

---

## Claude's Discretion

- GSD re-roadmap mechanism (in-place edit of ROADMAP/REQUIREMENTS/STATE vs `/gsd:new-milestone`) —
  chose in-place edit, committed separately.
- `CredentialResolver` interface shape, `jsonschema` draft, runtime aggregator-schema caching,
  `execute()` signature, failed-`tool_call` row shape, per-product GWS operation granularity,
  Composio SDK-vs-MCP binding, Nango self-host depth, OAuth refresh mechanics (CONTEXT "Claude's
  Discretion").
- **OBS-01 tool-event spans → close in Phase 4 (D-10):** Claude's inference (the close-now/defer
  question was in a rejected AskUserQuestion). Defensible — STATE.md's original deferral named Phase 4
  as the target. Surfaced in the confirm summary so the user can veto.

## Deferred Ideas

- Reference-adapter breadth → Phase 5 (TOOL-03): Webflow, Bitscale, Cal.com, Clockify, Beehiiv direct;
  Xero via aggregator. Plus heavy aggregator provider matrix + write-through-aggregator.
- Self-improvement → Phase 6 (SI-01/02): eval harness + AI-BOM-on-promotion.
- Deeper Slack interaction surface (slash commands, richer approval UX) — possible separate ingress
  item; not in scope now.
- v2: live GCP provisioning + FinOps; production hardening.
