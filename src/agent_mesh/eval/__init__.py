"""Evaluation surfaces for the self-improvement loop.

The default-lane held-out scoring engine lives in
``agent_mesh.services.eval_harness`` (creds-free, deterministic). This package
carries the **opt-in `live`-lane** LLM-judge dimension (SI-01d) in
``agent_mesh.eval.judges`` — position-bias control (order-swap), human-calibrated
TPR/FPR, a finite-sample Type-I gate, and a close-margin non-sole-arbiter guard.

Importing this package (or ``judges``) is creds-free and dep-light: every heavy
optional dependency (langfuse, the model-gateway chat stack) is imported lazily
inside the function that needs it, mirroring ``agent_mesh.observability``. The
judge logic is only EXERCISED behind the ``live_creds`` fixture + ``live`` marker;
the default ``make test`` lane (``pytest -m "not live"``) imports none of it.
"""
