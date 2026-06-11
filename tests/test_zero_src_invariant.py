"""Durable zero-`src/` milestone guardrail — env-gated loud-skip git-diff assertion.

This phase (and the milestone it carries) is **config / .env / docs / tests only**:
no `src/` change. P10 enforced the same invariant as a ONE-SHOT bash gate, not
durable CI (10-SECURITY.md Audit Note 1). This test makes it durable WITHOUT the
two failure modes of the naive formulations:

  * **Hardcoded base SHA** = a time-bomb: it would break the next legitimate
    src-touching milestone's ``make test`` the moment that milestone edits ``src/``.
  * **Branch-relative ``main...HEAD``** = vacuous on ``main`` (where ``make test``
    runs post-merge — the three-dot diff is empty there).

The only formulation that mirrors the repo's loud-skip convention AND avoids both
traps is **env-gated**: read ``ZERO_SRC_BASE`` from the environment; when unset,
``pytest.skip`` (loud-skip, exactly like ``conftest.py`` ``pg_dsn`` /
``TEST_DATABASE_URL`` at :75-88) so default ``make test`` stays green on any box.
When set, assert ``git diff $ZERO_SRC_BASE..HEAD -- src/`` is EMPTY.

OPERATOR / CI: export ``ZERO_SRC_BASE=<phase-base-SHA>`` (the pre-phase base —
this milestone's is ``5092323``, the HEAD recorded at planning, untouched by any
docs/plan commit) for the ENFORCING run:

    ZERO_SRC_BASE=5092323 .venv/bin/python -m pytest tests/test_zero_src_invariant.py -x

Default ``make test`` loud-skips this test. The SHA is NOT baked into the file —
it is operator/CI-supplied so the next src-touching milestone is unaffected.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]


def test_no_src_change_since_phase_base():
    """``git diff $ZERO_SRC_BASE..HEAD -- src/`` is empty (zero `src/` change).

    Loud-skips when ``ZERO_SRC_BASE`` is unset — mirroring the ``pg_dsn`` /
    ``TEST_DATABASE_URL`` convention so default ``make test`` needs no external
    state and stays green. The enforcing run supplies the phase-base SHA.
    """
    base = os.getenv("ZERO_SRC_BASE")
    if not base:
        pytest.skip(
            "ZERO_SRC_BASE unset; durable zero-src assertion needs the phase-base SHA"
        )
    out = subprocess.run(
        ["git", "diff", f"{base}..HEAD", "--", "src/"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out == "", f"src/ changed since {base} (zero-src guardrail breached):\n{out}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
