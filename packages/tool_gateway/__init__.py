"""Tool Gateway.

The ONLY code in this repo that:
  - reads tool credentials from env / Secrets Manager,
  - calls third-party tool APIs (Slack write, Monday, Sheets, tl;dv, etc.),
  - redacts secrets at the prompt/log boundary.

Activities ask the Tool Gateway by handle. The Tool Gateway enforces tool
trust tiers (read_safe / read_sensitive / write_revocable /
write_destructive / external_egress) and refuses calls above the caller's
authorized tier.
"""

from packages.tool_gateway.gateway import ToolGateway, ToolHandle

__all__ = ["ToolGateway", "ToolHandle"]
