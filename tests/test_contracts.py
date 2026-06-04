import pytest

from agent_mesh.contracts.enums import TaskState, ToolCategory
from agent_mesh.contracts.lifecycle import (
    IllegalTransition,
    assert_transition,
    can_transition,
    is_terminal,
)
from agent_mesh.contracts.models import CONTRACT_MODELS, TaskRequest


def test_all_contract_models_emit_json_schema():
    for name, model in CONTRACT_MODELS.items():
        schema = model.model_json_schema()
        assert schema["type"] == "object", name
        assert "properties" in schema, name


def test_task_request_round_trips():
    req = TaskRequest.model_validate(
        {
            "tenant_id": "t",
            "client_slug": "c",
            "entrypoint": "api",
            "requester": {"requester_id": "u1", "entrypoint": "api"},
            "prompt": "hello",
        }
    )
    assert req.entrypoint == "api"
    assert req.model_route_profile == "mixed-cascade"


def test_legal_transition():
    assert can_transition(TaskState.RECEIVED, TaskState.QUEUED)
    assert can_transition(TaskState.RUNNING, TaskState.AWAITING_APPROVAL)
    assert can_transition(TaskState.AWAITING_APPROVAL, TaskState.APPROVED)


def test_illegal_transition_rejected():
    assert not can_transition(TaskState.COMPLETED, TaskState.RUNNING)
    with pytest.raises(IllegalTransition):
        assert_transition(TaskState.COMPLETED, TaskState.RUNNING)


def test_terminal_states():
    assert is_terminal(TaskState.COMPLETED)
    assert is_terminal(TaskState.REJECTED)
    assert not is_terminal(TaskState.RUNNING)


def test_write_categories_classified():
    assert ToolCategory.WRITE.value == "write"
    assert ToolCategory.READ.value == "read"
