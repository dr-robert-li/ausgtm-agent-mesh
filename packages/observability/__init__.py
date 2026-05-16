"""Observability: OpenTelemetry setup and the five log streams.

The five streams are first-class persistence:
  - Event       — state transitions, ingress/egress, lifecycle.
  - Decision    — spawn allow/deny, HITL trigger, kill-switch trips.
  - Action      — tool calls, model calls (redacted).
  - Validation  — Contract Validator verdicts (shape).
  - Evaluation  — Evaluator verdicts (meaning).

A Task must be fully reconstructable from these streams alone — that
invariant is exercised in tests/observability/.
"""
