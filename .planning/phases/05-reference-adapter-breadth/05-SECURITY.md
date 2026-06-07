---
phase: 05
slug: reference-adapter-breadth
status: secured
threats_open: 0
threats_total: 21
threats_closed: 21
asvs_level: 1
register_authored_at_plan_time: true
created: 2026-06-07
---

# Phase 05 — Security

> Per-phase security contract for Reference Adapter Breadth (TOOL-03): 5 direct
> adapters (Webflow, Bitscale, Cal.com, Clockify, Beehiiv) + Xero via the Composio
> aggregator. Register authored at plan time across all 7 PLAN.md `<threat_model>`
> blocks; verified against the implementation by gsd-security-auditor.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| manifest → gateway loader | tool declarations (categories, approval flags, schema refs, op names) become runtime authority | tool policy / approval flags |
| manifest op name → adapter `_OPS` key | a name mismatch silently makes an op unreachable (no load-time error) | routing identity |
| gateway → provider API (Webflow/Bitscale/Cal.com/Clockify/Beehiiv) | resolved credential + agent params cross to a real SaaS surface | API key/token (secret) + write payloads |
| gateway → Composio Tool Router → Xero | `COMPOSIO_API_KEY` brokers Xero OAuth; a financial write crosses to a real accounting surface | secret + financial write payload |
| adapter → credential | secret resolved by the gateway, injected as `credential`; must never be logged/returned | API secret |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation (verified) | Status |
|-----------|----------|-----------|-------------|------------------------|--------|
| T-05-01-01 | Tampering | write-class manifest entry with `approval_required:false` | mitigate | `ToolSpec.validate()` raises for WRITE_CATEGORIES without approval (`gateway.py:47-53`), called per spec at load | closed |
| T-05-01-02 | Spoofing | manifest op name diverging from adapter `_OPS` key → unreachable op | mitigate | op-name set frozen by 05-01; credential-docs guard verifies `_LIVE_TEST_FILES`/docs match | closed |
| T-05-01-03 | Tampering | Xero financial write routed through shared `nango.py` | mitigate | manifest flips Xero to `composio_aggregator`; `nango.py` untouched; create stays `approval_required:true` | closed |
| T-05-01-SC | Tampering (supply chain) | new pip install | mitigate | no new `pyproject` extra; 5 direct adapters use core `httpx`; Xero rides existing `composio` extra | closed |
| T-05-01-04 | Information disclosure | schema files leaking real resource ids | **accept** | schemas use generic shapes; `REPLACE_WITH_*` placeholders live only in the manifest; no live ids committed (grep-verified) | closed |
| T-05-02-01 | Tampering | Webflow create publishing a live CMS item not a draft | mitigate | adapter forces `isDraft:true` unconditionally (`webflow.py:108`); default-lane test asserts override | closed |
| T-05-02-02 | EoP | Webflow create without approval | mitigate | manifest `publishing → approval_required`; enforced at load | closed |
| T-05-02-03 | Information disclosure | `WEBFLOW_API_TOKEN` leaking into logs/results | mitigate | passed as `credential`, never returned; no `os.getenv` (AST-verified) | closed |
| T-05-03-01 | EoP / Denial of wallet | Bitscale `run_grid` auto-burning paid credits | mitigate | live lane READS-ONLY (`grep run_grid test_bitscale_live.py` == 0 call sites); default test uses fake transport; `REPLACE_WITH_*` placeholder guard raises before the credit-POST (`bitscale.py`, 80e6d4e) | closed |
| T-05-03-02 | EoP | `run_grid` without approval | mitigate | manifest `write → approval_required`; enforced at load | closed |
| T-05-03-03 | Information disclosure | Bitscale `X-API-Key` leaking | mitigate | passed as `credential`, never returned; no `os.getenv` (AST-verified) | closed |
| T-05-04-01 | EoP | Cal.com `create_booking` without approval | mitigate | manifest `write → approval_required`; enforced at load | closed |
| T-05-04-02 | Information disclosure | `CALCOM_API_KEY` leaking | mitigate | passed as `credential`, never returned; no `os.getenv` (AST-verified) | closed |
| T-05-04-03 | Denial of service | missing/wrong `cal-api-version` 400-ing every call | mitigate | version pinned as module constant + default-lane header test on both ops | closed |
| T-05-05-01 | Information disclosure | `CLOCKIFY_API_KEY` leaking | mitigate | passed as `credential`, never returned; `clockify.py` does not import `os` (AST-verified) | closed |
| T-05-05-02 | Information disclosure | reading another workspace's time entries via spoofed ids | **accept** | `workspace_id`/`user_id` come exclusively from operator-controlled `resource_bindings`, never free agent params; read-only, low value | closed |
| T-05-06-01 | Tampering | Beehiiv create publishing a live post not a draft | mitigate | adapter forces `status:"draft"` unconditionally (`beehiiv.py:82`); default-lane test asserts override of caller status | closed |
| T-05-06-02 | EoP | Beehiiv `create_post` without approval | mitigate | manifest `publishing → approval_required`; enforced at load | closed |
| T-05-06-03 | Information disclosure | `BEEHIIV_API_KEY` leaking | mitigate | passed as `credential`, never returned; no `os.getenv` (AST-verified) | closed |
| T-05-07-01 | EoP | `xero_create_invoice` auto-finalising (not DRAFT) | mitigate | **code-enforced**: `composio._enforce_financial_draft` forces `Status:DRAFT` on `category==FINANCIAL` before dispatch and rejects any non-DRAFT `Status` loudly; 5 default-lane tests (commit at secure-phase) | closed |
| T-05-07-02 | Repudiation | success criterion 4 silently unenforced if guard lists not extended | mitigate | credential-docs guard floor self-test (12 env / 10 docs / 10 live-test / 9 anchors) fails if under-extended; 5 tests pass | closed |
| T-05-07-03 | Tampering | guard reddening intermediate merges if extended too early | mitigate | extension landed in the final plan after all referenced artifacts existed; passes on that merge only | closed |
| T-05-07-04 | Information disclosure | `COMPOSIO_API_KEY` leaking | mitigate | resolved only inside `execute()`, never returned; Xero reuses the existing key (no new secret surface) | closed |

*Status: open · closed*
*Disposition: mitigate (implementation verified) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-05-01 | T-05-01-04 | Schemas carry only generic shapes; real resource ids live as `REPLACE_WITH_*` placeholders in the manifest, replaced by operators at deploy time. No live ids in the repo (grep-verified). | requester (POC) | 2026-06-07 |
| AR-05-02 | T-05-05-02 | Clockify is read-only; `workspace_id`/`user_id` are operator-bound `resource_bindings`, not free agent input, so cross-workspace reads require operator misconfiguration, not agent action. Low value, read-only. | requester (POC) | 2026-06-07 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit 2026-06-07

| Metric | Count |
|--------|-------|
| Threats found | 21 |
| Closed | 21 |
| Open | 0 |

- Auditor (gsd-security-auditor, sonnet) verified 20/21 mitigations against source on first pass; flagged **T-05-07-01 OPEN** — the Xero DRAFT-only clause was documented but not code-enforced (the verb-agnostic `composio.py` passed `params` verbatim; draft rested on Xero's API default + the approval gate, which the FORCE stance rejects).
- Resolution (operator decision: *targeted guard in composio.py*): added `_enforce_financial_draft`, a category-gated (not provider-specific) cross-cutting rule that forces `Status:DRAFT` and rejects any non-DRAFT `Status` before dispatch — the aggregator-seam counterpart of webflow/beehiiv draft-force. 5 default-lane tests added; `xero.md` updated to cite the code enforcement. Full suite 247 passed, 6 skipped.
- The human-in-the-loop, payload-hash-bound approval gate remains the **primary** control for every write/financial/publishing tool; the in-code draft-forces are defence-in-depth.
- **ASVS L1.** All write-class tools require approval (enforced at load). No credential is logged or returned by any adapter (AST-verified: zero `os.getenv`/`os.environ` reads in adapter source).
