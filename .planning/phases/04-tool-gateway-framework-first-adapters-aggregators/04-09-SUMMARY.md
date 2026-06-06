---
phase: 04-tool-gateway-framework-first-adapters-aggregators
plan: 09
subsystem: tool-gateway-credentials-docs
tags: [credentials, docs, live-lane, drift-guard, D-12, D-11, TOOL-01, TOOL-04]
requires:
  - "docs/credentials/{hubspot,google_workspace,composio,nango}.md (04-05/06/07/08)"
  - "tests/test_{hubspot,gws,composio,nango}_live.py (the live-lane env enumeration)"
provides:
  - "docs/credentials/README.md — single discoverable per-provider credential/scope index (D-12)"
  - "per-provider opt-in live-lane matrix (D-11)"
  - "tests/test_credential_docs.py — drift-resistant completeness guard"
affects:
  - "RUNBOOK.md (Credentials & live lane pointer)"
tech-stack:
  added: []
  patterns:
    - "doc-completeness guard derives the env var set from source (live tests + adapters), not a hardcoded list"
    - "non-vacuous floor + anchor assertions so an empty/partial scan can never pass green"
key-files:
  created:
    - "docs/credentials/README.md"
    - "tests/test_credential_docs.py"
  modified:
    - "RUNBOOK.md"
decisions:
  - "Derive the live-lane env var set from the four live-test files (clean in-scope enumeration) UNIONED with adapter os.getenv reads — NOT from manifest credential_secret_name (which contaminates with out-of-scope Xero/Webflow/Bitscale/Cal.com/Clockify/Beehiiv providers that have no adapter or doc this phase)."
  - "Scan live-test files by all-caps-underscore literal SHAPE (not just direct os.getenv calls) to catch Nango's tuple-collected _REQUIRED_ENV form; verified zero false positives."
  - "Guard asserts a non-empty floor (>=7) + four credential anchors so the completeness check can never pass vacuously against a broken scan."
metrics:
  duration: "~15 min"
  completed: "2026-06-06"
  tasks: 1
  files: 3
---

# Phase 04 Plan 09: Credential Index + Opt-in Matrix + Drift Guard Summary

Tied the four per-provider credential docs into a single discoverable index
(`docs/credentials/README.md`, the D-12 deliverable), documented the per-provider
opt-in live-lane matrix (D-11), linked it from RUNBOOK, and added a drift-resistant
completeness guard that derives the live-lane env var set from source so the deliverable
cannot silently drift when a new env var is added to an existing in-scope adapter or
live test. (A wholly new fifth provider with its own live-test file is out of the
four-file scan scope by deliberate design — globbing all `test_*_live.py` would wrongly
pull in the model/gateway-credential-axis tests `test_cascade_live.py` /
`test_langfuse_seed_live.py`, a different credential axis per 04-PATTERNS.)

## What was built

- **`docs/credentials/README.md`** — the credential index a human reads to supply creds
  for the live lane. States the default lane is creds-free and live calls are
  per-provider opt-in; a matrix maps each provider (HubSpot, Google Workspace across all
  six products, Composio, Nango) to its env var(s), operation category (read /
  approval-gated write), per-provider setup doc, and independent skip behaviour; a full
  enumeration table of all seven live-lane env vars
  (`HUBSPOT_PRIVATE_APP_TOKEN`, `GOOGLE_WORKSPACE_OAUTH`, `COMPOSIO_API_KEY`,
  `NANGO_SECRET_KEY`, `NANGO_HOST`, `NANGO_CONNECTION_ID`, `NANGO_PROVIDER_CONFIG_KEY`);
  and how to run the live lane (`pytest -m live`) with each provider skipping
  independently. No real secret values committed (env-var names + placeholders only,
  threat T-04-09-01).
- **`RUNBOOK.md`** — new "Credentials & live lane" section pointing at the index.
- **`tests/test_credential_docs.py`** — five default-lane guard tests. Derives the
  live-lane env var set by text-scanning the four live-test files (all-caps underscore
  literals, covering both direct `os.getenv("VAR")` and tuple-collected forms) unioned
  with adapter-source `os.getenv` reads; asserts the set is non-empty, meets a >=7 floor
  and contains four credential anchors (non-vacuous); asserts every derived var appears
  in the index; asserts the index links all four per-provider docs; asserts the four
  docs exist and are non-empty on disk; and asserts the D-11 opt-in/skip matrix is
  documented. Import-free and creds-free (repo files read as text only).

## Verification

- `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live" tests/test_credential_docs.py` — 5 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest -q -m "not live"` — **215 passed, 6 skipped, 9 deselected** (baseline 210 + 5 new; still green and creds-free).
- All seven env var names present in `docs/credentials/README.md`; all four doc filenames linked; `grep -ci credential RUNBOOK.md` = 10.

## Deviations from Plan

None - plan executed exactly as written. (One implementation refinement within the task:
the env-var scan initially matched only direct `os.getenv("VAR")` calls and missed
Nango's tuple-collected `_REQUIRED_ENV`; switched the live-test scan to match the
all-caps-underscore literal shape, which yields exactly the seven in-scope vars with no
false positives.)

## Threat coverage

- T-04-09-01 (info disclosure): index uses env-var names + placeholders only; no real
  secret values; the guard references names, never values.
- T-04-09-02 (repudiation / undocumented var drift): `tests/test_credential_docs.py`
  derives the env var set from source and fails if any is undocumented — the drift guard.

## Known Stubs

None. (This plan ships documentation + a guard test; no execution path.)

## Commits

- `eb7bbd4` docs(04-09): credential index + opt-in matrix + RUNBOOK link + drift guard

## Self-Check: PASSED

- FOUND: docs/credentials/README.md
- FOUND: tests/test_credential_docs.py
- FOUND: RUNBOOK.md (modified)
- FOUND commit: eb7bbd4
