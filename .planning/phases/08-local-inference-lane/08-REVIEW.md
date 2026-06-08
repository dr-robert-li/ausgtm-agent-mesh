---
phase: 08-local-inference-lane
reviewed: 2026-06-08T11:35:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - config/model_gateway.cloud.yaml
  - config/model_gateway.vllm.yaml
  - config/model_gateway.ollama.yaml
  - Makefile
  - tests/test_local_profiles.py
  - RUNBOOK.md
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-06-08T11:35:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Phase 8 adds a local/offline inference lane — two LiteLLM `model_gateway` profiles
(vLLM, Ollama), Makefile run/swap targets, a config-validation test, and a RUNBOOK
section — with zero `src/` change as required. The core deliverables are correct and
the stated constraints hold under verification:

- **Egress-free local profiles (verified):** both `model_gateway.vllm.yaml` and
  `model_gateway.ollama.yaml` use loopback-only `api_base` on every route
  (`http://localhost:8000/v1` for vLLM, `http://localhost:11434` for Ollama), drop
  the cloud-only `high-complexity-vertex` route, and carry no cloud *provider*
  env-refs. The retained `master_key: os.environ/MODEL_GATEWAY_MASTER_KEY` is
  proxy-auth indirection, not a provider credential, and `build_router` never reads
  `general_settings` — so it is correctly inert and not an egress leak.
- **"Never CI" constraint holds (verified):** `run-vllm` / `run-ollama` are standalone
  Makefile targets, absent from the `test:` recipe (`pytest -q -m "not live"`) and
  every other CI path.
- **LOCAL-04 test (verified):** runs creds-free and offline; `build_router` constructs
  the real `litellm.Router` with no network call. 8 passed locally.
- **Deployment-name parity (verified):** all three frozen names
  (`low/medium/high-complexity`) match the `TIER_TO_DEPLOYMENT` seam verbatim.

The two warnings below concern incomplete operator disclosure (the file-swap breaks a
sibling test in its transient state) and a documented-but-real coverage gap in the
validation test. Neither blocks the phase; both should be addressed before this lane is
handed to operators.

## Warnings

### WR-01: File-swap leaves `make test` failing the d06 egress-chokepoint guard — undisclosed in RUNBOOK

**File:** `RUNBOOK.md:119-137`, `Makefile:90-95`
**Issue:** Activating a local profile (`make use-vllm` / `make use-ollama`) copies the
loopback profile onto the tracked `config/model_gateway.config.yaml`. While that profile
is active, `tests/test_d06_chokepoint.py` — which asserts every active-config route
egresses through the `os.environ/CF_AIG_WRAPPER_URL` indirection — **fails**. Verified
empirically:

```
=== swapped to vllm; running d06 chokepoint ===
FAILED tests/test_d06_chokepoint.py::test_every_route_api_base_resolves_to_cf_wrapper_when_enabled
FAILED tests/test_d06_chokepoint.py::test_every_route_api_base_uses_the_env_indirection
2 failed, 6 passed
```

So an operator who runs `make use-vllm` and then `make test` (the natural next step
after switching to the local lane) sees two confusing failures. The RUNBOOK honestly
discloses the *git-dirty* consequence of the swap (RUNBOOK.md:132-137) but does **not**
disclose the *`make test`* consequence. The test itself is correct — it is in fact
*protective* (it catches an accidental commit with a local profile active). The defect
is incomplete disclosure, not the test.

**Fix:** Add one line to the RUNBOOK "Selecting a profile (file-swap)" section, e.g.:

```markdown
> While a local profile is active, `tests/test_d06_chokepoint.py` will fail (it asserts
> the active config egresses through the Cloudflare wrapper, which the loopback profile
> deliberately does not). This is expected — run `make use-cloud` before `make test`.
> The failure is protective: it also blocks an accidental commit with a local profile active.
```

### WR-02: LOCAL-04 inspects only `api_base`; a route-level cloud credential ref would not be caught here

**File:** `tests/test_local_profiles.py:56-66`
**Issue:** `test_every_route_api_base_is_loopback` and the `_CLOUD_MARKERS` negative
guard inspect only `litellm_params.api_base`. A future regression that re-introduced a
cloud egress through a *different* field — e.g. a route-level
`api_key: os.environ/ANTHROPIC_API_KEY` or a `vertex_project` ref while keeping a
loopback `api_base` — would pass all four LOCAL-04 assertions. The profiles are clean
today, and the test docstring (lines 16-18) **explicitly** scopes the full
no-cloud-env-ref sweep to Plan 01's grep gate and Phase 11. This is therefore an
accurate, documented coverage boundary rather than an oversight — but it is worth
recording because the test's name ("loopback / no cloud markers") reads broader than its
actual reach, and a reader could over-trust it as a complete egress guard.

**Fix:** Either (a) leave as-is and rely on Phase 11 for the full sweep (acceptable per
the documented scope), or (b) cheaply harden by sweeping the whole `litellm_params` dict
for `_CLOUD_MARKERS`, not just `api_base`:

```python
for r in cfg["model_list"]:
    blob = str(r["litellm_params"])
    assert not any(m in blob for m in _CLOUD_MARKERS), (
        f"{name}/{r['model_name']}: cloud marker in litellm_params {blob!r}"
    )
```

## Info

### IN-01: Loopback assertion uses `startswith`, which a `localhost`-prefixed FQDN could satisfy

**File:** `tests/test_local_profiles.py:37,61`
**Issue:** `_LOOPBACK = ("http://localhost", "http://127.0.0.1")` combined with
`ab.startswith(_LOOPBACK)` means a string like `http://localhost.evil.example/` would
pass the loopback check. This is **not** a realistic threat — the input is
repo-authored config, not attacker-controlled, and no plausible developer regression
produces a `localhost`-prefixed FQDN. Recorded only as a test-hardening nicety.
**Fix:** If hardening, anchor to a host boundary — e.g. require the char after the
loopback host to be `:`, `/`, or end-of-string — or parse with `urllib.parse.urlsplit`
and assert `hostname in {"localhost", "127.0.0.1"}`.

### IN-02: `run-ollama` runs `ollama pull` before `ollama serve`

**File:** `Makefile:83-84`, `RUNBOOK.md:108`
**Issue:** `run-ollama: ollama pull $(OLLAMA_MODEL) && ollama serve` pulls before
serving. On a box where no Ollama daemon is already running, `ollama pull` needs a
reachable server and can fail before `ollama serve` is ever reached. In practice many
Ollama installs run the daemon as a background service so this works, and the target is
explicitly best-effort/operator-only (D-07), so this is low priority.
**Fix:** Optionally document the "daemon must be running for `pull`" assumption in the
RUNBOOK, or note that operators on a cold box may need `ollama serve` in one shell and
`ollama pull` in another.

---

_Reviewed: 2026-06-08T11:35:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
