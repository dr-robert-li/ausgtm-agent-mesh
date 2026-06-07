---
status: partial
phase: 06-self-improvement
source: [06-VERIFICATION.md]
started: 2026-06-08T00:00:00Z
updated: 2026-06-08T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. SI-01d live-lane LLM-judge under real provider credentials
expected: `make test-live` (with real provider credentials configured) collects and passes the 5 `tests/test_judges_live.py` tests, exercising the live-lane LLM judge end-to-end: order-swap position-bias symmetry (a candidate win counts only when both orderings agree), TPR/FPR calibration against the human-labelled set with the trusted-judge gate, the finite-sample one-sided binomial Type-I gate, and the close-margin non-sole-arbiter guard (judge defers to the deterministic 06-02 gate within the margin). All model calls route through the model gateway (`get_chat_model`, GW-02 chokepoint) — never a provider SDK directly.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
