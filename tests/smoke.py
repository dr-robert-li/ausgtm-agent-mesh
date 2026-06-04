"""Local end-to-end smoke check — no database, no network, no model credentials.

Exercises: schema export, ingress -> shared task service -> dispatch -> worker
-> approval pause -> approval decision -> resume -> completion, for both a
write-gated task and a read-only task. Run with ``make smoke``.
"""

from __future__ import annotations

from agent_mesh.contracts.enums import ApprovalDecision
from agent_mesh.contracts.export_schemas import export
from agent_mesh.services.dispatch import InProcessDispatcher
from agent_mesh.services.repository import InMemoryRepository
from agent_mesh.services.task_service import TaskService, request_from_mcp, request_from_slack
from agent_mesh.worker.runner import Worker


def main() -> None:
    written = export()
    print(f"[schemas] exported {len(written)} contract schemas")

    repo = InMemoryRepository()
    dispatcher = InProcessDispatcher()
    svc = TaskService(repo=repo, dispatcher=dispatcher)
    worker = Worker(repo=repo)

    # 1) Write-gated path (Slack)
    task = svc.create_task(
        request_from_slack(
            tenant_id="t", client_slug="c", slack_user_id="U1", slack_channel_id="C1",
            text="create a monday item for kickoff",
        )
    )
    assert worker.process(task.task_id) == "awaiting_approval"
    (approval_id,) = list(repo._approvals.keys())
    svc.submit_approval_decision(approval_id, ApprovalDecision.APPROVED, "slack:U1", "slack")
    assert worker.process(task.task_id) == "completed"
    print("[write] Slack task paused for approval, approved, completed")

    # 2) Read-only path (MCP) — no approval
    task2 = svc.create_task(
        request_from_mcp(tenant_id="t", client_slug="c", mcp_subject="svc", text="summarize notes")
    )
    assert worker.process(task2.task_id) == "completed"
    print("[read] MCP task completed without approval")

    print("SMOKE OK")


if __name__ == "__main__":
    main()
