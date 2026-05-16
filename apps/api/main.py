"""FastAPI app — the system of record and the *only* write surface.

Slack and MCP must call into this app rather than touching Temporal,
the DB, or the Tool Gateway directly.

This stub gives shape but no real handlers — wire routes in subsequent PRs.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="ausgtm-agent-mesh API",
    version="0.1.0",
    description=(
        "System of record for the Agentic Mesh POC. The Orchestrator "
        "(Temporal) is the only mutator of Task.state; this API exposes the "
        "write surface that starts/observes that work."
    ),
)


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", tags=["meta"])
async def readyz() -> dict[str, str]:
    # TODO: probe Postgres + Temporal connectivity.
    return {"status": "ok"}


# --- Routers (to be added) ---------------------------------------------------
# from apps.api.routes import tasks, policies, routines, spawn_ledger, hitl
# app.include_router(tasks.router, prefix="/v1/tasks", tags=["tasks"])
# app.include_router(policies.router, prefix="/v1/policies", tags=["policies"])
# app.include_router(routines.router, prefix="/v1/routines", tags=["routines"])
# app.include_router(spawn_ledger.router, prefix="/v1/spawn-ledger", tags=["supervisor"])
# app.include_router(hitl.router, prefix="/v1/hitl", tags=["hitl"])
