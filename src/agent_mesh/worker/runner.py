"""Worker runner: consume a task id and execute the mesh with approval gating.

Execution model:
1. Move task RECEIVED/QUEUED -> RUNNING.
2. Run the LangGraph + Deep Agents orchestration adapter.
3. For each *proposed write*, create a gated ToolCall + open an approval. The
   task pauses in AWAITING_APPROVAL and the worker returns — the run resumes
   when an approval decision is dispatched back (durable, survives restart).
4. If there are no pending writes, complete the task.

When resumed after approval, write tool calls whose approval is APPROVED (and
whose payload hash still matches) execute through the Tool Gateway; the task then
completes.
"""

from __future__ import annotations

from agent_mesh.contracts.enums import (
    ApprovalDecision,
    TaskState,
    ToolCallStatus,
    ToolCategory,
)
from agent_mesh.contracts.lifecycle import is_terminal
from agent_mesh.contracts.models import ToolCall
from agent_mesh.services import approvals
from agent_mesh.services.repository import Repository, get_repository
from agent_mesh.tools.credentials import CredentialResolver, EnvCredentialResolver
from agent_mesh.tools.gateway import ToolGateway
from agent_mesh.worker.orchestrator import resume_mesh, run_mesh


class Worker:
    def __init__(
        self,
        repo: Repository | None = None,
        tool_gateway: ToolGateway | None = None,
        resolver: CredentialResolver | None = None,
    ) -> None:
        self._repo = repo or get_repository()
        self._gateway = tool_gateway
        # The credential-resolution authority for execute() (D-02). Defaults to the
        # env-backed resolver: creds-free by default (every secret resolves to None ->
        # the gateway degrades to the deterministic stub, D-11), prod swaps to a
        # SecretManagerResolver behind the same Protocol. The resolver is shared by BOTH
        # the ungated read loop and the gated write execution — neither receives raw
        # credentials; the gateway resolves them at call time only.
        self._resolver = resolver or EnvCredentialResolver()

    def process(self, task_id: str) -> str:
        """Process or resume a single task. Returns the resulting state value."""
        task = self._repo.get_task(task_id)
        if task is None:
            raise KeyError(f"unknown task {task_id}")
        if is_terminal(task.state):
            return str(task.state)

        # Resume path: a previously gated task has just been approved.
        if task.state == TaskState.APPROVED.value or task.state == TaskState.APPROVED:
            return self._resume_after_approval(task_id)

        # Fresh run.
        self._repo.transition_task(task_id, TaskState.RUNNING, note="worker picked up task")
        result = run_mesh(task)

        # Governed-halt guard (03-04): a budget halt makes ``run_mesh`` transition the
        # task to the FAILED terminal state itself. Without this re-check the next
        # ``transition_task(COMPLETED)`` would hit ``assert_transition(FAILED, COMPLETED)``
        # and raise ``IllegalTransition``. Re-fetch and short-circuit on any terminal
        # state so the orchestrator-owned terminal outcome is honoured.
        current = self._repo.get_task(task_id)
        if current is not None and is_terminal(current.state):
            return str(current.state)

        # ----------------------------------------------------------------------
        # Ungated read loop (audit item A, T-04-04-01). The INVERSE of the write
        # gate below: proposed reads execute IMMEDIATELY and UNGATED — they NEVER
        # touch the approval ledger (no build_approval_request / open_approval /
        # is_approved). Each read is recorded as a category=read / is_read=True
        # ToolCall in EXECUTED status (tenant-scoped, DUR-02), and a STRING summary
        # (never the raw result dict — T-04-04-03) is appended to the evidence the
        # write-gate approval request below carries. A write smuggled into
        # proposed_reads is still recorded category=READ unconditionally (T-04-04-02);
        # the manifest's write-class invariant + the gateway's own validation remain.
        read_evidence: list[str] = list(result.evidence)
        for proposed in result.proposed_reads:
            read_call = ToolCall(
                task_id=task_id,
                tenant_id=task.tenant_id,
                tool_name=proposed["tool_name"],
                category=ToolCategory.READ,
                approval_required=False,
                is_read=True,
                status=ToolCallStatus.EXECUTED,
                parameters=proposed.get("parameters", {}),
                requester_id=task.requester.requester_id,
            )
            result_dict = self._execute(read_call)  # ungated; no approval ledger
            executed = read_call.model_copy(update={"result": result_dict})
            self._repo.upsert_tool_call(executed)
            read_evidence.append(
                f"read {read_call.tool_name}: {len(result_dict)} field(s)"
            )

        if not result.proposed_writes:
            done = self._repo.transition_task(
                task_id, TaskState.COMPLETED, note="no write actions required"
            )
            updated = done.model_copy(update={"result_summary": result.summary})
            self._repo.create_task(updated)  # upsert
            return str(updated.state)

        # Gate each proposed write behind an approval.
        issued_tokens: dict[str, str] = {}
        for proposed in result.proposed_writes:
            call = ToolCall(
                task_id=task_id,
                tenant_id=task.tenant_id,
                tool_name=proposed["tool_name"],
                category=ToolCategory(proposed["category"]),
                approval_required=True,
                status=ToolCallStatus.AWAITING_APPROVAL,
                parameters=proposed.get("parameters", {}),
                requester_id=task.requester.requester_id,
            )
            self._repo.upsert_tool_call(call)
            request = approvals.build_approval_request(
                call, summary=f"Approve write: {call.tool_name}", evidence=read_evidence
            )
            # Live issuance path: unpack (record, token) and carry the token to
            # the requester. The scaffold has no Slack/MCP postback channel yet,
            # so we stash the token durably on the task metadata keyed by record
            # id (round-trips via task_metadata). The approval callback presents
            # this exact token; real-time Slack/MCP delivery is deferred.
            record, token = approvals.open_approval(self._repo, request)
            issued_tokens[record.approval_record_id] = token
            call = call.model_copy(update={"approval_record_id": record.approval_record_id})
            self._repo.upsert_tool_call(call)

        if issued_tokens:
            current = self._repo.get_task(task_id)
            assert current is not None
            metadata = dict(current.metadata)
            tokens = dict(metadata.get(approvals.APPROVAL_TOKENS_METADATA_KEY, {}))
            tokens.update(issued_tokens)
            metadata[approvals.APPROVAL_TOKENS_METADATA_KEY] = tokens
            self._repo.create_task(current.model_copy(update={"metadata": metadata}))  # upsert

        self._repo.transition_task(
            task_id, TaskState.AWAITING_APPROVAL, note="paused for write approval"
        )
        return str(TaskState.AWAITING_APPROVAL.value)

    def _resume_after_approval(self, task_id: str) -> str:
        task = self._repo.get_task(task_id)
        assert task is not None
        # Resume the paused mesh graph from its durable checkpoint (ORCH-03). On the real
        # stack this dispatches Command(resume=True) so the write_gate interrupt RELEASES
        # and the graph runs to terminal; on the stub env it is a terminal no-op. `decision`
        # is a SINGLE already-verified boolean: the task reached APPROVED only because
        # verify_approval_token + record_decision already ran at the endpoint, and the
        # write_gate node only RELEASES the interrupt (it never executes the write). We pass
        # NO approver_id into resume — the approver is derived solely from the verified token
        # (SEC-01). The real per-call gate stays approvals.is_approved() below.
        resume_mesh(task, True)

        # Governed-halt guard (03-04): a budget halt on the resume path makes
        # ``resume_mesh`` transition the task to FAILED itself. Honour that terminal
        # outcome rather than forcing COMPLETED (which would raise IllegalTransition).
        current = self._repo.get_task(task_id)
        if current is not None and is_terminal(current.state):
            return str(current.state)

        # Execute any approved-and-unmodified write tool calls. This is the ONLY place a
        # write executes, gated by approvals.is_approved() payload re-hash (SEC-02a).
        for call in self._pending_calls(task_id, task.tenant_id):
            if call.approval_record_id is None:
                continue
            record = self._repo.get_approval(call.approval_record_id)
            if record is None:
                continue
            if approvals.is_approved(record, call.parameters):
                result = self._execute(call)
                executed = call.model_copy(
                    update={"status": ToolCallStatus.EXECUTED.value, "result": result}
                )
                self._repo.upsert_tool_call(executed)
            elif (
                record.decision == ApprovalDecision.REJECTED.value
                or record.decision == ApprovalDecision.REJECTED
            ):
                rejected = call.model_copy(update={"status": ToolCallStatus.REJECTED.value})
                self._repo.upsert_tool_call(rejected)

        done = self._repo.transition_task(
            task_id, TaskState.COMPLETED, note="completed after approval"
        )
        return str(done.state)

    def _pending_calls(self, task_id: str, tenant_id: str) -> list[ToolCall]:
        # Fetch tool calls through the protocol (tenant-scoped) so the resume
        # path works identically against the in-memory and SQL repositories.
        return self._repo.list_tool_calls(task_id, tenant_id)

    def _execute(self, call: ToolCall) -> dict:
        if self._gateway is None:
            return {
                "stub": True,
                "note": "no tool gateway configured; write not executed",
                "tool": call.tool_name,
            }
        # execute() takes the ToolCall (04-03 Pitfall 2 — carries task/tenant
        # correlation) and the Worker's resolver (04-04 item B). The resolver is the
        # credential-resolution authority: the gateway resolves the secret ONLY inside
        # execute() and never returns it (D-02). Creds-free by default — every secret
        # resolves to None -> the deterministic stub (D-11) — so both the ungated read
        # loop and the gated write path stay green and creds-free on the default lane.
        # The SAME call site serves reads and writes; governance (gate vs. ungated) is
        # decided by the CALLER, never here.
        return self._gateway.execute(call, resolver=self._resolver)
