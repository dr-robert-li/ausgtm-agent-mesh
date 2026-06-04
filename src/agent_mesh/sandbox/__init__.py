"""Prompt-to-code sandbox.

Executes generated code in an isolated subprocess with conservative default
limits and produces *proposed patches / artifacts only*. Applying any change
(file overwrite, SaaS mutation, repo commit, external send) requires an approval
recorded in the approval ledger.

POC SCOPE / SAFETY NOTE: this subprocess sandbox is suitable for local dev and a
low-trust POC. It is NOT a production isolation boundary. Production MUST run
generated code in hardened containers (gVisor/Kata or equivalent) with no host
FS/network access, scoped short-lived service accounts, and default-deny egress.
See docs/production-readiness-caveats.md §1.
"""

from agent_mesh.sandbox.executor import (
    CodeExecutionResult,
    SandboxLimits,
    execute_code,
    propose_patch,
)

__all__ = ["CodeExecutionResult", "SandboxLimits", "execute_code", "propose_patch"]
