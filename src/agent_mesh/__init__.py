"""Reusable autonomous agent mesh POC package.

This package contains the *reusable platform* skeleton: the canonical task
contract, ingress services, the shared task service layer, the worker/AG2
orchestration adapter, and the prompt-to-code sandbox. Client-specific SaaS
adapters live behind the Tool Gateway contract and are supplied per deployment
through tool pack manifests, not baked into this package.
"""

__version__ = "0.2.0"
