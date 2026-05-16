"""Model Gateway.

Routes model calls to a provider based on policy-supplied tier (S/M/L).

Primary path: direct Anthropic Claude Agent SDK.
Fallbacks: AWS Bedrock, GCP Vertex AI.

Activities import from here; workflows must not.
"""

from packages.model_gateway.base import ModelProvider, ModelRequest, ModelResponse

__all__ = ["ModelProvider", "ModelRequest", "ModelResponse"]
