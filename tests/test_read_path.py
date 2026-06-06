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

from agent_mesh.services.task_service import request_from_slack
from agent_mesh.worker.orchestrator import OrchestrationResult, _run_stub


def _task(prompt: str):
    return request_from_slack(
        tenant_id="t",
        client_slug="c",
        slack_user_id="U1",
        slack_channel_id="C1",
        text=prompt,
    )


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
