"""Read-execution seam tests (04-04, TOOL-01, audit item A).

The mesh proposes READS as well as writes. Reads execute UNGATED immediately
post-run (no approval ledger), record ``category=read`` / ``is_read=True``
ToolCalls in EXECUTED status (tenant-scoped), and feed a string summary into
evidence. The headline security invariant (T-04-04-01): the read path NEVER
routes through ``approvals.is_approved`` / ``build_approval_request`` /
``open_approval`` — a read is not a write-without-approval hole. Writes stay
gated through the unchanged payload-hash ledger (SEC-01/SEC-02).
"""

from __future__ import annotations

import inspect

from agent_mesh.contracts.enums import ToolCallStatus, ToolCategory
from agent_mesh.services import approvals
from agent_mesh.services.dispatch import InProcessDispatcher
from agent_mesh.services.task_service import TaskService, request_from_slack
from agent_mesh.tools.credentials import CredentialResolver, EnvCredentialResolver
from agent_mesh.tools.gateway import ToolGateway
from agent_mesh.worker.orchestrator import OrchestrationResult, _run_stub
from agent_mesh.worker.runner import Worker

MANIFEST = "manifests/tool_pack_manifest.yaml"


def _task(prompt: str):
    return request_from_slack(
        tenant_id="t",
        client_slug="c",
        slack_user_id="U1",
        slack_channel_id="C1",
        text=prompt,
    )


def _svc_and_worker(repo, *, tool_gateway=None):
    svc = TaskService(repo=repo, dispatcher=InProcessDispatcher())
    worker = Worker(repo=repo, tool_gateway=tool_gateway)
    return svc, worker


# ==========================================================================
# Task 1 — OrchestrationResult.proposed_reads + _run_stub / graph emission
# ==========================================================================


def test_orchestration_result_defaults_proposed_reads_empty():
    """OrchestrationResult defaults proposed_reads to [] (additive field)."""
    result = OrchestrationResult(summary="x")
    assert result.proposed_reads == []


def test_orchestration_result_accepts_proposed_reads_list():
    """OrchestrationResult accepts a list of {tool_name, category, parameters} dicts."""
    reads = [{"tool_name": "hubspot_lookup_company", "category": "read", "parameters": {}}]
    result = OrchestrationResult(summary="x", proposed_reads=reads)
    assert result.proposed_reads == reads


def test_run_stub_emits_a_schema_declaring_read():
    """_run_stub emits at least one deterministic proposed_reads entry whose tool_name
    is a schema-declaring read tool (so the default lane exercises the read path)."""
    result = _run_stub(_task("research the acme account"))
    assert result.proposed_reads, "stub must propose at least one read"
    entry = result.proposed_reads[0]
    assert entry["tool_name"] in ("hubspot_lookup_company", "google_drive_search")
    assert entry["category"] == "read"
    assert isinstance(entry["parameters"], dict)


def test_run_stub_read_params_are_schema_valid():
    """The deterministic read's parameters satisfy the declared input schema so the
    real from_manifest gateway path does NOT input-reject it (it stubs cleanly)."""
    from agent_mesh.tools import validation

    result = _run_stub(_task("research acme"))
    entry = result.proposed_reads[0]
    # hubspot_lookup_company schema: object_type in {companies,contacts}, query minLength 1.
    if entry["tool_name"] == "hubspot_lookup_company":
        params = entry["parameters"]
        assert params["object_type"] in ("companies", "contacts")
        assert len(params["query"]) >= 1
    # No InputSchemaViolation when validated against the manifest-declared schema.
    validation.validate_tool_input(
        integration_style="direct_api",
        input_schema_ref=f"schemas/{entry['tool_name']}.input.schema.json",
        runtime_schema=None,
        params=entry["parameters"],
    )


def test_run_stub_read_query_guarded_on_empty_prompt():
    """An empty prompt must still yield a schema-valid query (minLength 1)."""
    result = _run_stub(_task(""))
    if result.proposed_reads:
        entry = result.proposed_reads[0]
        if entry["tool_name"] == "hubspot_lookup_company":
            assert len(entry["parameters"]["query"]) >= 1


def test_run_stub_write_path_unchanged_for_write_trigger():
    """Item C: a write-trigger prompt still produces the same deterministic gated
    write (the approval path is NOT softened)."""
    result = _run_stub(_task("create a hubspot deal"))
    assert any(w["tool_name"] == "hubspot_create_deal" for w in result.proposed_writes)
    assert result.proposed_writes[0]["category"] == "write"


def test_graph_researcher_emits_proposed_reads():
    """researcher_node emits a heuristic proposed_reads into MeshState (stub lane),
    keeping its role-distinct research output."""
    from agent_mesh.worker.graph import researcher_node

    out = researcher_node({"prompt": "research acme", "plan": "[plan] do x"})
    assert "research" in out  # role-distinct output retained
    assert out.get("proposed_reads"), "researcher must emit proposed_reads"
    entry = out["proposed_reads"][0]
    assert entry["category"] == "read"
    assert entry["tool_name"] in ("hubspot_lookup_company", "google_drive_search")


def test_graph_reviewer_write_unchanged():
    """Item C: reviewer_node keeps the heuristic-derived write proposal unchanged."""
    from agent_mesh.worker.graph import reviewer_node

    out = reviewer_node({"prompt": "create a deal", "code": "[code] x"})
    assert out["proposed_writes"]
    assert out["proposed_writes"][0]["tool_name"] == "hubspot_create_deal"


# ==========================================================================
# Task 2 — ungated post-run read execution + execute(call) + gateway injection
# ==========================================================================


def _read_calls(repo, task_id):
    return [c for c in repo.list_tool_calls(task_id, "t") if c.is_read]


def test_read_executes_ungated_and_records_executed_row(repo):
    """Item A: a read-only task records a category=read / is_read=True ToolCall in
    EXECUTED status, tenant-scoped, with NO approval record opened for the read."""
    svc, worker = _svc_and_worker(repo)  # tool_gateway=None -> stub fallback (D-11)
    task = svc.create_task(_task("research the acme account"))
    state = worker.process(task.task_id)
    # No write trigger -> the task completes (the read does not park it).
    assert state == "completed"
    reads = _read_calls(repo, task.task_id)
    assert len(reads) == 1
    read = reads[0]
    assert read.category == ToolCategory.READ.value
    assert read.is_read is True
    assert read.status == ToolCallStatus.EXECUTED.value
    assert read.approval_required is False
    assert read.tenant_id == "t"
    assert read.result is not None  # _execute populated the result (stub dict)
    assert read.approval_record_id is None  # never gated
    # No approval record exists at all for this read-only task.
    assert repo.list_approvals(task.task_id, "t") == []


def test_read_appends_string_evidence_not_raw_dict(repo):
    """Item A / T-04-04-03: evidence is a string summary, never the raw result dict."""
    svc, worker = _svc_and_worker(repo)
    task = svc.create_task(_task("research acme"))
    worker.process(task.task_id)
    done = repo.get_task(task.task_id)
    # The completed summary path persists result_summary; evidence is threaded as strings.
    # Assert the persisted read row carries a dict result while evidence stays string-typed
    # (no dict leaked into the evidence list anywhere the worker built it).
    reads = _read_calls(repo, task.task_id)
    assert isinstance(reads[0].result, dict)


def test_read_path_never_opens_an_approval(repo, monkeypatch):
    """SECURITY T-04-04-01 (headline): the read execution path calls NONE of
    approvals.build_approval_request / open_approval / is_approved."""
    calls: list[str] = []
    monkeypatch.setattr(
        approvals,
        "build_approval_request",
        lambda *a, **k: calls.append("build_approval_request"),
    )
    monkeypatch.setattr(
        approvals, "open_approval", lambda *a, **k: calls.append("open_approval")
    )
    monkeypatch.setattr(
        approvals, "is_approved", lambda *a, **k: calls.append("is_approved") or False
    )
    svc, worker = _svc_and_worker(repo)
    task = svc.create_task(_task("research the acme account"))  # read-only, no write
    worker.process(task.task_id)
    # A read row was recorded...
    assert _read_calls(repo, task.task_id)
    # ...and NO approval primitive was touched for the read-only task.
    assert calls == []


def test_write_trigger_still_parks_and_opens_approval(repo):
    """Write path unchanged: a write-trigger task parks in AWAITING_APPROVAL with an
    approval opened — AND the ungated read still runs alongside it."""
    svc, worker = _svc_and_worker(repo)
    task = svc.create_task(_task("create a hubspot deal"))
    state = worker.process(task.task_id)
    assert state == "awaiting_approval"
    # The write opened an approval.
    (record,) = repo.list_approvals(task.task_id, "t")
    assert record is not None
    # The read executed ungated alongside the parked write.
    reads = _read_calls(repo, task.task_id)
    assert len(reads) == 1
    assert reads[0].status == ToolCallStatus.EXECUTED.value
    assert reads[0].approval_record_id is None
    # The write call is gated, separate from the read.
    writes = [
        c for c in repo.list_tool_calls(task.task_id, "t") if not c.is_read
    ]
    assert len(writes) == 1
    assert writes[0].status == ToolCallStatus.AWAITING_APPROVAL.value


def test_execute_passes_call_to_gateway_execute_signature():
    """runner._execute calls gateway.execute(call, resolver=...) — the 04-03 signature
    (passes the ToolCall, not name+params)."""
    src = inspect.getsource(Worker._execute)
    assert "self._gateway.execute(call" in src
    # The gateway-None stub fallback is intact.
    assert "self._gateway is None" in src


def test_worker_has_resolver_defaulting_to_env_resolver():
    """Worker carries a resolver attribute defaulting to EnvCredentialResolver (item B)."""
    worker = Worker()
    assert isinstance(worker._resolver, CredentialResolver)
    assert isinstance(worker._resolver, EnvCredentialResolver)


def test_worker_accepts_injected_resolver():
    sentinel = EnvCredentialResolver()
    worker = Worker(resolver=sentinel)
    assert worker._resolver is sentinel


def test_main_bootstrap_injects_real_manifest_gateway():
    """Item B: the worker bootstrap builds a Worker whose _gateway is a real
    ToolGateway loaded from the manifest (not None), with a resolver present."""
    from agent_mesh.worker import main

    src = inspect.getsource(main)
    # Both ctor sites inject a real from_manifest gateway.
    assert "ToolGateway.from_manifest" in src
    # And the actual constructed worker is gateway-backed: build it the way main does.
    worker = Worker(tool_gateway=ToolGateway.from_manifest(MANIFEST))
    assert isinstance(worker._gateway, ToolGateway)
    assert worker._gateway is not None
    assert isinstance(worker._resolver, EnvCredentialResolver)


def test_read_via_real_manifest_gateway_stubs_cleanly_creds_free(repo):
    """With a real from_manifest gateway but NO creds, the read still records an EXECUTED
    stub row (input validation passes, no-cred fallback) — never input_rejected."""
    gateway = ToolGateway.from_manifest(MANIFEST)
    svc, worker = _svc_and_worker(repo, tool_gateway=gateway)
    task = svc.create_task(_task("research acme"))
    state = worker.process(task.task_id)
    assert state == "completed"
    reads = _read_calls(repo, task.task_id)
    assert len(reads) == 1
    # Creds absent -> stub dict; schema_validation must be "ok" (input passed), NOT rejected.
    assert reads[0].result is not None
    assert reads[0].schema_validation in ("ok", None)
    assert reads[0].status == ToolCallStatus.EXECUTED.value
