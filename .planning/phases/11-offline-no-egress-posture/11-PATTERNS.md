# Phase 11: Offline / No-Egress Posture - Pattern Map

**Mapped:** 2026-06-11
**Files analyzed:** 6 (2 EXTEND, 4 NEW config/test/docs — zero `src/` change)
**Analogs found:** 6 / 6 (5 strong file analogs; 1 mechanism is research-derived — see deny-guard note)

> **Scope guardrail (carried, do NOT regress):** config / .env / docs / tests only.
> No `src/` edit. Every assertion targets the **cloud-LLM/model-gateway egress path
> only** (Vertex AI, Anthropic-direct, Cloudflare AI Gateway) — never a blanket
> socket/network block. Service-DNS (`vllm:8000`, `ollama:11434`), loopback,
> Postgres, self-hosted Langfuse, and SaaS adapters are all legitimate.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tests/test_local_profiles.py` (EXTEND) | test (config-validation) | file-I/O / transform | itself + `tests/test_d06_chokepoint.py` | exact (same file) |
| `tests/test_offline_compose_env.py` (NEW) | test (config-validation) | file-I/O / transform | `tests/test_compose_config.py` (shape) + `test_d06_chokepoint.py` (config-load) | role-match |
| `tests/test_offline_deny_guard.py` (NEW) | test (autouse fixture) | event-driven (connect-seam intercept) | `tests/conftest.py` `live_creds`/`pg_dsn` (loud-skip/creds-gating ONLY — see note) | partial (mechanism research-derived) |
| `tests/test_zero_src_invariant.py` (NEW) | test (env-gated loud-skip) | batch (subprocess `git diff`) | `tests/conftest.py` `pg_dsn` (:75-88) | role-match |
| `.env.offline.example` (NEW) | config (operator posture) | — | `.env.example` (:51-59 cloud-LLM key block) | exact (derive-from) |
| `RUNBOOK.md` (EXTEND) | docs | — | `RUNBOOK.md` existing P8/P9/P10 local sections | exact (same file) |

> **`.env.offline.example` assertion target (load-bearing correction).** If a test
> sweeps `.env.offline.example`, its analog is the **valued-key check** in
> `test_offline_compose_env.py` (`_CLOUD_KEY_NAMES`, key-present-but-empty = OK), NOT
> the `test_local_profiles.py` substring sweep. Reason: the posture file legitimately
> contains the cloud-LLM key *names* (`CF_AIG_WRAPPER_URL=`, `ANTHROPIC_API_KEY=`)
> blank by design — a substring sweep (`"anthropic" in text`) would trip on the file's
> own intentionally-blank keys. The check must be "key present but **valued**", not
> "marker substring present". (Planner may fold this into `test_offline_compose_env.py`.)

## Pattern Assignments

### `tests/test_local_profiles.py` (EXTEND — D-01) — test, file-I/O

**Analog:** itself (the LOCAL-04 seam its own docstring designates as "Phase 11's job", :16-18) + `tests/test_d06_chokepoint.py` (the INVERTED config-load pattern).

**Marker/allowlist/name tuples to extend** (`test_local_profiles.py:29-46`):
```python
_PROFILES = {
    "vllm": _REPO / "config" / "model_gateway.vllm.yaml",
    "ollama": _REPO / "config" / "model_gateway.ollama.yaml",
}
_NAMES = {"low-complexity", "medium-complexity", "high-complexity"}
_LOOPBACK = ("http://localhost", "http://127.0.0.1")
_CLOUD_MARKERS = (
    "os.environ/CF_AIG_WRAPPER_URL",
    "vertex_ai",
    "anthropic",
    "googleapis.com",
    "anthropic.com",
)
```
Extension per D-01: add the 2 compose profiles to `_PROFILES`
(`model_gateway.vllm.compose.yaml`, `model_gateway.cpu.compose.yaml` — both
confirmed present); add `_SERVICE_DNS = ("http://vllm:8000", "http://ollama:11434")`
and allow `_LOOPBACK + _SERVICE_DNS`; add a **whole-file** `read_text()` deny sweep
alongside the existing api_base-scoped one.

**Per-profile parametrized loop to mirror** (`test_local_profiles.py:56-66`):
```python
@pytest.mark.parametrize("name", list(_PROFILES))
def test_every_route_api_base_is_loopback(name):
    cfg = yaml.safe_load(_PROFILES[name].read_text())
    for r in cfg["model_list"]:
        ab = r["litellm_params"]["api_base"]
        assert ab.startswith(_LOOPBACK), (
            f"{name}/{r['model_name']}: api_base {ab!r} not loopback"
        )
        assert not any(m in ab for m in _CLOUD_MARKERS), (
            f"{name}/{r['model_name']}: cloud marker in api_base {ab!r}"
        )
```
For the 2 compose profiles, `startswith` must accept `_SERVICE_DNS` too (service-DNS
is egress-free in-stack — D-01), so the assertion becomes `ab.startswith(_LOOPBACK + _SERVICE_DNS)`.

**Negative control to mirror** — `test_d06_chokepoint.py:180-208`
(`test_guard_detects_a_synthetic_offender`). That test proves a guard is non-vacuous
by parsing a *synthetic* offender snippet. Phase 11 inverts the source: read the REAL
`config/model_gateway.cloud.yaml` (confirmed to contain 8 cloud-marker hits) and assert
it DOES trip `_CLOUD_MARKERS` — so a future edit that empties the marker tuple fails loudly.

---

### `tests/test_offline_compose_env.py` (NEW — D-04) — test, file-I/O

**Analog:** `tests/test_compose_config.py` (the only CI-wired P10 artifact — its
module shape and `make test` collection behavior) + `test_d06_chokepoint.py` config-load.

**Target** — `docker-compose.yml` `api` env block (`docker-compose.yml:40-49`) and
`worker` env block (`:75-83`). Both currently set only `DATABASE_URL` (@postgres,
in-stack DNS), `LANGFUSE_HOST` (@langfuse-web), blank `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`,
and `TMPDIR` — all legitimate; the sweep passes today and catches a FUTURE cloud key/api_base.

**Valued-key semantics (the D-04 / posture-env shared check):** assert each named
cloud-LLM key is absent OR blank-valued, and no env VALUE carries a cloud host. This
is the analog the `.env.offline.example` sweep also points at:
```python
_CLOUD_KEY_NAMES = ("ANTHROPIC_API_KEY", "VERTEX_PROJECT_ID", "VERTEX_LOCATION",
                    "CF_AIG_WRAPPER_URL", "MODEL_GATEWAY_SHARED_SECRET")
# key present is OK; key VALUED (non-empty) is the violation
for k, v in items:
    if k in _CLOUD_KEY_NAMES:
        assert not v, f"{svc}: cloud-LLM key {k} has a VALUED entry {v!r}"
```
Compose `environment:` may be a dict or a `KEY=VALUE` list — normalize both (see
RESEARCH:353-354). Reads `docker-compose.yml` text statically with `yaml.safe_load`;
**no docker daemon** (unlike `test_compose_config.py`, which shells `docker compose config`).

**Module-level loud-skip shape** — `test_compose_config.py:34-37`. This NEW file
parses YAML statically so it needs NO docker binary and should NOT carry the
`skipif(shutil.which("docker"))`; the skip analog is shown for the deny-guard/zero-src
files. (Mirror the docstring discipline of `test_compose_config.py:1-19`: state what is
asserted vs out of scope.)

---

### `tests/test_offline_deny_guard.py` (NEW — D-02) — test, autouse fixture / connect-seam

**Analog (PARTIAL):** `tests/conftest.py` `live_creds` (:124-136) + `pg_dsn` (:75-88).

> **No-analog for the MECHANISM.** `conftest.py` has **no `autouse=True` fixture** and
> no `monkeypatch(socket.getaddrinfo)` — every fixture there is plain (`pg_dsn`,
> `live_creds`, `sql_repo`, `stub_router`). The autouse + `socket.getaddrinfo` patch is
> **research-derived**; the planner takes the mechanism from RESEARCH "Code Examples"
> (the deny-guard fixture, RESEARCH:242-312), NOT from a repo file. The repo analogs
> below cover only the loud-skip / creds-gating shell around it.

**Creds-gating analog (Pitfall 4 — do NOT break `make test-live`)** — mirror
`conftest.py:124-136` `live_creds`: gate the autouse guard OFF when real provider creds
are present, the same skip-when-present shape:
```python
@pytest.fixture
def live_creds() -> None:
    if not any(
        os.getenv(var)
        for var in ("ANTHROPIC_API_KEY", "VERTEX_PROJECT_ID", "CF_AIG_WRAPPER_URL")
    ):
        pytest.skip("no provider/gateway creds exported; live tests require them")
```
The deny-guard inverts the polarity (no-op/skip when creds ARE present, so `-m live`
real cloud calls aren't blocked) but reuses the same env-var probe set. Keep the
fixture **module-scoped autouse** in this file, not in root `conftest.py` (Pitfall 4).

**Representative-path analog (non-vacuous proof, Pitfall 5)** —
`test_local_profiles.py:79-90` already builds a real Router offline from a local
profile (`build_router(str(_PROFILES[name]))`, no provider call). Reuse that exact
`build_router` call UNDER the guard, drive one completion through the loopback profile,
and assert the guard does NOT fire (connection-refused to localhost is acceptable; an
`"OFFLINE deny"` is not). Pair with an `anthropic/` positive control (sync + async) that
MUST trip.

---

### `tests/test_zero_src_invariant.py` (NEW — durable zero-`src/` guardrail) — test, batch

**Analog:** `tests/conftest.py` `pg_dsn` (:75-88) — the env-gated loud-skip-when-unset shape:
```python
@pytest.fixture
def pg_dsn() -> str:
    dsn = os.getenv("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL unset; SQL-backed tests require a local Postgres")
    ...
    return dsn
```
Mirror exactly: read `ZERO_SRC_BASE` from env, `pytest.skip(...)` when unset, else
`subprocess.run(["git", "diff", f"{base}..HEAD", "--", "src/"], ...)` and assert empty
stdout (RESEARCH:315-334). Default `make test` loud-skips; the phase-verify/CI run
exports the base SHA.

> **Do NOT hardcode the base SHA.** `ZERO_SRC_BASE` is operator/CI-set at execution
> (RESEARCH A4, MEDIUM-risk). A hardcoded always-on base is a time-bomb that breaks the
> next src-touching milestone's `make test`; branch-relative `main...HEAD` is vacuous on
> `main`. Env-gated loud-skip is the only non-time-bomb formulation. (Current HEAD is
> `5092323`, the likely base — but the planner/operator sets the exact value, the test
> does not bake it.)

---

### `.env.offline.example` (NEW — D-03) — config, operator posture

**Analog:** `.env.example` cloud-LLM key block (`.env.example:51-59`):
```
MODEL_GATEWAY_MASTER_KEY=
MODEL_GATEWAY_SHARED_SECRET=
CF_AIG_WRAPPER_URL=
ANTHROPIC_API_KEY=
VERTEX_PROJECT_ID=
VERTEX_LOCATION=australia-southeast1
GOOGLE_APPLICATION_CREDENTIALS=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
```
**Offline transform (D-03):** blank the cloud-LLM/gateway creds —
`CF_AIG_WRAPPER_URL=`, `ANTHROPIC_API_KEY=`, `VERTEX_PROJECT_ID=`, and **also blank
`VERTEX_LOCATION`** (it currently carries `australia-southeast1` at `:56` — a value, so
the valued-key check would flag it). Keep `MODEL_GATEWAY_BASE_URL` local
(`http://localhost:4000`, `.env.example:26`). Local model `api_base` is NOT a new env
var — it comes from the `use-vllm`/`use-ollama` file-swap (Makefile). **SaaS/tool-pack
creds (`COMPOSIO_API_KEY`, `BITSCALE_API_KEY`) stay as-is** — offline zeroes only
cloud-LLM/gateway creds. Carry forward the COMPOSE-02 documentation note style already
present in `.env.example:35-40`.

---

### `RUNBOOK.md` (EXTEND — D-03) — docs

**Analog:** the existing local-section structure in `RUNBOOK.md` —
`## Local inference lane` (:96), `## Local data & telemetry plane` (:184),
`## Full-stack local compose` (:250), `## Credentials & live lane` (:340).
**Insertion anchor:** add `## Offline / no-egress posture` near `:250`/`:340` (after
"Full-stack local compose", before/near "Credentials & live lane"). Mirror those
sections' shape: what the posture is, how to express it (`cp .env.offline.example .env`
+ `make use-vllm`/`use-ollama`), how to verify (`make test` runs the sweep + deny-guard;
`ZERO_SRC_BASE=<sha> make test` for the durable zero-src assertion), and the scope
caveat ("offline = no cloud-hosted LLM inference, not blocking all outbound").

## Shared Patterns

### Config-load + assert-over-content (no live model call)
**Source:** `tests/test_local_profiles.py:51,58` and `tests/test_d06_chokepoint.py:46-49`
(`yaml.safe_load(path.read_text())` / `with open(_CONFIG_PATH) as fh: yaml.safe_load(fh)`).
**Apply to:** all D-01/D-04/posture-env sweeps. Read YAML/compose/.env off disk, assert
over content; never construct a live provider call. `build_router` is lazy (no provider
call at construction — `test_local_profiles.py:79-90` proves it), so config tests run
egress-free.

### Loud-skip-when-unavailable (keep `make test` green on any box)
**Source:** `tests/conftest.py:75-88` (`pg_dsn`, fixture `pytest.skip`) and
`tests/test_compose_config.py:34-37` (module-level `skipif(shutil.which(...))`).
**Apply to:** `test_zero_src_invariant.py` (env-gated on `ZERO_SRC_BASE`, fixture-style
skip) and any docker/binary-gated test (module-level skipif). Two mechanisms, one
principle. The CI-wired tests slot into `make test` (`pytest -q -m "not live"`).

### Creds-gating to protect `-m live` (Pitfall 4)
**Source:** `tests/conftest.py:124-136` (`live_creds` env-var probe over
`ANTHROPIC_API_KEY`/`VERTEX_PROJECT_ID`/`CF_AIG_WRAPPER_URL`).
**Apply to:** the deny-guard fixture — reuse this exact probe set to no-op the guard
when real creds are present, so `make test-live` real cloud calls are not blocked. Keep
the autouse guard module-scoped, never in root `conftest.py`.

### Non-vacuous negative control
**Source:** `tests/test_d06_chokepoint.py:180-208` (`test_guard_detects_a_synthetic_offender`).
**Apply to:** the D-01 sweep — assert `config/model_gateway.cloud.yaml` (real file, 8
marker hits, confirmed) DOES trip `_CLOUD_MARKERS`; and the deny-guard `anthropic/`
positive control (sync + async). Proves the guards discriminate, not vacuously pass.

## No Analog Found

| Concern | Role | Data Flow | Reason / Source |
|---------|------|-----------|-----------------|
| `autouse` + `monkeypatch(socket.getaddrinfo)` deny mechanism | test fixture | connect-seam intercept | No `autouse` fixture and no socket-patch exists anywhere in the repo (`conftest.py` fixtures are all plain). Mechanism is **research-derived** — planner uses RESEARCH:242-312 (the empirically-proven `getaddrinfo` seam, covers sync+async). Repo analogs cover only the loud-skip/creds-gating shell. |

## Metadata

**Analog search scope:** `tests/` (test_local_profiles, test_d06_chokepoint, conftest,
test_compose_config), `config/` (6 gateway profiles confirmed present), `docker-compose.yml`
(api/worker env blocks), `.env.example`, `RUNBOOK.md`.
**Files scanned:** 6 analog files read in full + 6 config profiles + docker-compose.yml header/env blocks confirmed.
**Negative-control source confirmed:** `config/model_gateway.cloud.yaml` — 8 cloud-marker hits.
**Current HEAD (likely zero-src base, operator-set):** `5092323`.
**Pattern extraction date:** 2026-06-11
