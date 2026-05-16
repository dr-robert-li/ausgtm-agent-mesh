"""Policy, Evaluator, Validator services.

Policy compiles tenant + scope rules into the limits/budgets attached to
each task. The Swarm Supervisor consults the policy engine for the
five-step gate (policy / budget / risk / provenance / marginal-utility).

L-tier is mandatory for policy compilation, agentic policy enforcement,
and the Evaluator. No silent downgrade.
"""
