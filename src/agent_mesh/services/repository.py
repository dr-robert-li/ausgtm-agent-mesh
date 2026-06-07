"""Persistence abstraction.

The POC ships an in-memory repository so the whole mesh is importable and
testable without a database. A Postgres-backed implementation slots in behind
the same ``Repository`` protocol; the migrations in ``migrations/`` define the
target schema. ``get_repository`` chooses based on ``DATABASE_URL``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from threading import RLock
from typing import Protocol

from agent_mesh.contracts.enums import TaskState
from agent_mesh.contracts.lifecycle import assert_transition
from agent_mesh.contracts.models import (
    AIBOMSnapshot,
    ApprovalRecord,
    BudgetEvent,
    EvaluationResult,
    GatewayEvent,
    PromotionRecord,
    SelfImprovementProposal,
    TaskEvent,
    TaskRecord,
    ToolCall,
)


class ConcurrentModification(RuntimeError):
    """Raised when a guarded state transition loses a race.

    ``transition_task`` performs the state change with a conditional
    ``UPDATE ... WHERE task_id=%s AND state=%s``. If another connection already
    advanced the task out of the expected state, the UPDATE matches no row and
    this is raised so the caller can retry rather than silently double-advancing
    the state and appending a duplicate audit event (WR-02)."""


class Repository(Protocol):
    def create_task(self, task: TaskRecord) -> TaskRecord: ...
    def get_task(self, task_id: str) -> TaskRecord | None: ...
    def transition_task(
        self, task_id: str, target: TaskState, note: str | None = None
    ) -> TaskRecord: ...
    def append_event(self, event: TaskEvent) -> TaskEvent: ...
    def list_events(self, task_id: str, tenant_id: str) -> list[TaskEvent]: ...
    def upsert_tool_call(self, call: ToolCall) -> ToolCall: ...
    def get_tool_call(self, tool_call_id: str) -> ToolCall | None: ...
    def list_tool_calls(self, task_id: str, tenant_id: str) -> list[ToolCall]: ...
    def upsert_approval(self, record: ApprovalRecord) -> ApprovalRecord: ...
    def get_approval(self, approval_record_id: str) -> ApprovalRecord | None: ...
    def list_approvals(self, task_id: str, tenant_id: str) -> list[ApprovalRecord]: ...
    def upsert_proposal(
        self, proposal: SelfImprovementProposal
    ) -> SelfImprovementProposal: ...
    def get_proposal(self, proposal_id: str) -> SelfImprovementProposal | None: ...
    def upsert_evaluation(self, evaluation: EvaluationResult) -> EvaluationResult: ...
    def get_evaluation(self, evaluation_id: str) -> EvaluationResult | None: ...
    def list_evaluations(
        self, proposal_id: str, tenant_id: str
    ) -> list[EvaluationResult]: ...
    def upsert_promotion(self, promotion: PromotionRecord) -> PromotionRecord: ...
    def get_promotion(self, promotion_id: str) -> PromotionRecord | None: ...
    # -- active-version pointer (SI-02b) + AI-BOM persistence (SI-02) --
    def current_active_version(self, tenant_id: str) -> str | None: ...
    def set_active_version(
        self, tenant_id: str, version: str, promotion_id: str | None = None
    ) -> None: ...
    def upsert_ai_bom(self, snapshot: AIBOMSnapshot) -> AIBOMSnapshot: ...
    def get_ai_bom(
        self, snapshot_id: str, tenant_id: str
    ) -> AIBOMSnapshot | None: ...
    # -- budget ledger + gateway events (GW-01 / D-04 / DUR-02) --
    def record_budget_event(self, event: BudgetEvent) -> BudgetEvent: ...
    def budget_month_to_date(
        self, tenant_id: str, budget_owner: str, since: datetime
    ) -> float: ...
    def record_gateway_event(self, event: GatewayEvent) -> GatewayEvent: ...
    def list_gateway_events(
        self, task_id: str, tenant_id: str
    ) -> list[GatewayEvent]: ...


class InMemoryRepository:
    """Thread-safe in-memory store for local dev and tests."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._tasks: dict[str, TaskRecord] = {}
        self._events: list[TaskEvent] = []
        self._tool_calls: dict[str, ToolCall] = {}
        self._approvals: dict[str, ApprovalRecord] = {}
        self._proposals: dict[str, SelfImprovementProposal] = {}
        self._evaluations: dict[str, EvaluationResult] = {}
        self._promotions: dict[str, PromotionRecord] = {}
        # tenant_id -> (active_version, promotion_id | None)
        self._active_version: dict[str, tuple[str, str | None]] = {}
        # snapshot_id -> AIBOMSnapshot
        self._ai_bom_snapshots: dict[str, AIBOMSnapshot] = {}
        self._budget_events: dict[str, BudgetEvent] = {}
        self._gateway_events: dict[str, GatewayEvent] = {}

    def create_task(self, task: TaskRecord) -> TaskRecord:
        with self._lock:
            self._tasks[task.task_id] = task
            return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def transition_task(
        self, task_id: str, target: TaskState, note: str | None = None
    ) -> TaskRecord:
        with self._lock:
            task = self._tasks[task_id]
            assert_transition(task.state, target)
            # Re-create with new state; models use enum values so coerce to value.
            updated = task.model_copy(
                update={
                    "state": target.value,
                    "updated_at": datetime.now(UTC),
                }
            )
            self._tasks[task_id] = updated
            self._events.append(
                TaskEvent(task_id=task_id, tenant_id=task.tenant_id, state=target, note=note)
            )
            return updated

    def append_event(self, event: TaskEvent) -> TaskEvent:
        with self._lock:
            self._events.append(event)
            return event

    def list_events(self, task_id: str, tenant_id: str) -> list[TaskEvent]:
        with self._lock:
            return [
                e
                for e in self._events
                if e.task_id == task_id and e.tenant_id == tenant_id
            ]

    def upsert_tool_call(self, call: ToolCall) -> ToolCall:
        with self._lock:
            self._tool_calls[call.tool_call_id] = call
            return call

    def get_tool_call(self, tool_call_id: str) -> ToolCall | None:
        with self._lock:
            return self._tool_calls.get(tool_call_id)

    def list_tool_calls(self, task_id: str, tenant_id: str) -> list[ToolCall]:
        with self._lock:
            return [
                c
                for c in self._tool_calls.values()
                if c.task_id == task_id and c.tenant_id == tenant_id
            ]

    def upsert_approval(self, record: ApprovalRecord) -> ApprovalRecord:
        with self._lock:
            self._approvals[record.approval_record_id] = record
            return record

    def get_approval(self, approval_record_id: str) -> ApprovalRecord | None:
        with self._lock:
            return self._approvals.get(approval_record_id)

    def list_approvals(self, task_id: str, tenant_id: str) -> list[ApprovalRecord]:
        with self._lock:
            return [
                r
                for r in self._approvals.values()
                if r.task_id == task_id and r.tenant_id == tenant_id
            ]

    def upsert_proposal(
        self, proposal: SelfImprovementProposal
    ) -> SelfImprovementProposal:
        with self._lock:
            self._proposals[proposal.proposal_id] = proposal
            return proposal

    def get_proposal(self, proposal_id: str) -> SelfImprovementProposal | None:
        with self._lock:
            return self._proposals.get(proposal_id)

    def upsert_evaluation(self, evaluation: EvaluationResult) -> EvaluationResult:
        with self._lock:
            self._evaluations[evaluation.evaluation_id] = evaluation
            return evaluation

    def get_evaluation(self, evaluation_id: str) -> EvaluationResult | None:
        with self._lock:
            return self._evaluations.get(evaluation_id)

    def list_evaluations(
        self, proposal_id: str, tenant_id: str
    ) -> list[EvaluationResult]:
        with self._lock:
            return [
                e
                for e in self._evaluations.values()
                if e.proposal_id == proposal_id and e.tenant_id == tenant_id
            ]

    def upsert_promotion(self, promotion: PromotionRecord) -> PromotionRecord:
        with self._lock:
            self._promotions[promotion.promotion_id] = promotion
            return promotion

    def get_promotion(self, promotion_id: str) -> PromotionRecord | None:
        with self._lock:
            return self._promotions.get(promotion_id)

    # -- active-version pointer (SI-02b) + AI-BOM persistence (SI-02) -------
    def current_active_version(self, tenant_id: str) -> str | None:
        with self._lock:
            # Tenant-scoped (DUR-02): never returns another tenant's pointer.
            entry = self._active_version.get(tenant_id)
            return entry[0] if entry is not None else None

    def set_active_version(
        self, tenant_id: str, version: str, promotion_id: str | None = None
    ) -> None:
        with self._lock:
            # Upsert semantics (mirrors upsert_promotion / the SQL ON CONFLICT).
            self._active_version[tenant_id] = (version, promotion_id)

    def upsert_ai_bom(self, snapshot: AIBOMSnapshot) -> AIBOMSnapshot:
        with self._lock:
            # ON CONFLICT DO NOTHING semantics: first write of a snapshot_id wins
            # (an AI-BOM snapshot is immutable at a point in time).
            self._ai_bom_snapshots.setdefault(snapshot.snapshot_id, snapshot)
            return snapshot

    def get_ai_bom(self, snapshot_id: str, tenant_id: str) -> AIBOMSnapshot | None:
        with self._lock:
            snap = self._ai_bom_snapshots.get(snapshot_id)
            # Tenant-scoped (DUR-02): a tenant-A snapshot is never returned for
            # tenant-B; unknown id returns None.
            if snap is None or snap.tenant_id != tenant_id:
                return None
            return snap

    # -- budget ledger + gateway events ------------------------------------
    def record_budget_event(self, event: BudgetEvent) -> BudgetEvent:
        with self._lock:
            # Append-only with ON CONFLICT DO NOTHING semantics: a re-record of the
            # same id must not double-count (mirrors the SQL ON CONFLICT clause).
            self._budget_events.setdefault(event.budget_event_id, event)
            return event

    def budget_month_to_date(
        self, tenant_id: str, budget_owner: str, since: datetime
    ) -> float:
        with self._lock:
            # Tenant-scoped SUM since `since` (DUR-02): never cross-tenant.
            return float(
                sum(
                    e.estimated_cost_usd
                    for e in self._budget_events.values()
                    if e.tenant_id == tenant_id
                    and e.budget_owner == budget_owner
                    and e.created_at >= since
                )
            )

    def record_gateway_event(self, event: GatewayEvent) -> GatewayEvent:
        with self._lock:
            self._gateway_events.setdefault(event.gateway_event_id, event)
            return event

    def list_gateway_events(self, task_id: str, tenant_id: str) -> list[GatewayEvent]:
        with self._lock:
            return sorted(
                (
                    e
                    for e in self._gateway_events.values()
                    if e.task_id == task_id and e.tenant_id == tenant_id
                ),
                key=lambda e: e.created_at,
            )


# ---------------------------------------------------------------------------
# Postgres-backed repository (DUR-01 durable state + DUR-02 tenant scoping)
# ---------------------------------------------------------------------------
# Mirrors InMemoryRepository method-for-method over the 0001/0002 schema using a
# single sync psycopg3 ConnectionPool. Migrations are applied EXTERNALLY (psql /
# make migrate); this class never self-applies them (keeps the LangGraph
# checkpointer's CONCURRENTLY/autocommit concern out of Phase 1). All value
# parameters use %s placeholders only — no string interpolation of values.


def _enum_value(value: object) -> str:
    """Return the string value for an Enum-or-str field (Pitfall 6).

    ``use_enum_values=True`` coerces enums to their values during *validation*,
    but a model constructed with an enum *default* (e.g. ``TaskState.RECEIVED``)
    keeps the bare enum. ``str(TaskState.RECEIVED)`` yields
    ``'TaskState.RECEIVED'`` for a str-mixin Enum, which would write garbage into
    a TEXT column and break Pydantic re-validation on read. Prefer ``.value``.
    """
    return value.value if isinstance(value, Enum) else str(value)


def _row_to_task(row: tuple) -> TaskRecord:
    (
        task_id,
        tenant_id,
        client_slug,
        entrypoint,
        session_id,
        requester,
        prompt,
        state,
        model_route_profile,
        result_summary,
        error,
        metadata,
        created_at,
        updated_at,
    ) = row
    return TaskRecord(
        task_id=task_id,
        tenant_id=tenant_id,
        client_slug=client_slug,
        entrypoint=entrypoint,
        requester=requester,
        session_id=session_id,
        prompt=prompt,
        state=state,
        model_route_profile=model_route_profile,
        result_summary=result_summary,
        error=error,
        metadata=metadata or {},
        created_at=created_at,
        updated_at=updated_at,
    )


def _row_to_event(row: tuple) -> TaskEvent:
    event_id, task_id, tenant_id, state, note, payload, created_at = row
    return TaskEvent(
        event_id=event_id,
        task_id=task_id,
        tenant_id=tenant_id,
        state=state,
        note=note,
        payload=payload or {},
        created_at=created_at,
    )


def _row_to_tool_call(row: tuple) -> ToolCall:
    (
        tool_call_id,
        task_id,
        tenant_id,
        tool_name,
        category,
        approval_required,
        status,
        parameters,
        result,
        requester_id,
        model_route,
        approval_record_id,
        integration_style,
        schema_validation,
        is_read,
        created_at,
    ) = row
    return ToolCall(
        tool_call_id=tool_call_id,
        task_id=task_id,
        tenant_id=tenant_id,
        tool_name=tool_name,
        category=category,
        approval_required=approval_required,
        status=status,
        parameters=parameters or {},
        result=result,
        requester_id=requester_id,
        model_route=model_route,
        approval_record_id=approval_record_id,
        integration_style=integration_style,
        schema_validation=schema_validation,
        is_read=is_read,
        created_at=created_at,
    )


def _row_to_approval(row: tuple) -> ApprovalRecord:
    (
        approval_record_id,
        approval_request_id,
        task_id,
        tenant_id,
        tool_call_id,
        decision,
        approver_id,
        channel,
        payload_hash,
        decided_at,
        created_at,
    ) = row
    return ApprovalRecord(
        approval_record_id=approval_record_id,
        approval_request_id=approval_request_id,
        task_id=task_id,
        tenant_id=tenant_id,
        tool_call_id=tool_call_id,
        decision=decision,
        approver_id=approver_id,
        channel=channel,
        payload_hash=payload_hash,
        decided_at=decided_at,
        created_at=created_at,
    )


def _row_to_proposal(row: tuple) -> SelfImprovementProposal:
    (
        proposal_id,
        tenant_id,
        client_slug,
        task_id,
        session_id,
        agent_id,
        proposal_type,
        risk_level,
        status,
        title,
        rationale,
        proposed_patch,
        target_ref,
        evidence_pointers,
        patch_hash,
        approval_record_id,
        metadata,
        created_at,
        updated_at,
    ) = row
    return SelfImprovementProposal(
        proposal_id=proposal_id,
        tenant_id=tenant_id,
        client_slug=client_slug,
        task_id=task_id,
        session_id=session_id,
        agent_id=agent_id,
        proposal_type=proposal_type,
        risk_level=risk_level,
        status=status,
        title=title,
        rationale=rationale,
        proposed_patch=proposed_patch,
        target_ref=target_ref,
        evidence_pointers=evidence_pointers or [],
        patch_hash=patch_hash,
        approval_record_id=approval_record_id,
        metadata=metadata or {},
        created_at=created_at,
        updated_at=updated_at,
    )


def _row_to_evaluation(row: tuple) -> EvaluationResult:
    (
        evaluation_id,
        proposal_id,
        tenant_id,
        passed,
        pending,
        checks,
        evaluator,
        summary,
        created_at,
    ) = row
    return EvaluationResult(
        evaluation_id=evaluation_id,
        proposal_id=proposal_id,
        tenant_id=tenant_id,
        passed=passed,
        pending=pending,
        checks=checks or [],
        evaluator=evaluator,
        summary=summary,
        created_at=created_at,
    )


def _row_to_promotion(row: tuple) -> PromotionRecord:
    (
        promotion_id,
        proposal_id,
        tenant_id,
        client_slug,
        approval_record_id,
        evaluation_id,
        promoted_version,
        previous_version,
        patch_hash,
        ai_bom_snapshot_id,
        rolled_back,
        rollback_reason,
        promoted_by,
        created_at,
    ) = row
    return PromotionRecord(
        promotion_id=promotion_id,
        proposal_id=proposal_id,
        tenant_id=tenant_id,
        client_slug=client_slug,
        approval_record_id=approval_record_id,
        evaluation_id=evaluation_id,
        promoted_version=promoted_version,
        previous_version=previous_version,
        patch_hash=patch_hash,
        ai_bom_snapshot_id=ai_bom_snapshot_id,
        rolled_back=rolled_back,
        rollback_reason=rollback_reason,
        promoted_by=promoted_by,
        created_at=created_at,
    )


def _row_to_ai_bom(row: tuple) -> AIBOMSnapshot:
    (
        snapshot_id,
        tenant_id,
        client_slug,
        version,
        agents,
        tools,
        skills,
        prompts,
        model_routes,
        created_at,
    ) = row
    return AIBOMSnapshot(
        snapshot_id=snapshot_id,
        tenant_id=tenant_id,
        client_slug=client_slug,
        version=version,
        agents=agents or [],
        tools=tools or [],
        skills=skills or [],
        prompts=prompts or [],
        model_routes=model_routes or {},
        created_at=created_at,
    )


def _row_to_budget_event(row: tuple) -> BudgetEvent:
    (
        budget_event_id,
        tenant_id,
        client_slug,
        budget_owner,
        task_id,
        model,
        prompt_tokens,
        completion_tokens,
        estimated_cost_usd,
        created_at,
    ) = row
    return BudgetEvent(
        budget_event_id=budget_event_id,
        tenant_id=tenant_id,
        client_slug=client_slug,
        budget_owner=budget_owner,
        task_id=task_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        # NUMERIC(12,6) comes back as Decimal; BudgetEvent.estimated_cost_usd is float.
        estimated_cost_usd=float(estimated_cost_usd),
        created_at=created_at,
    )


def _row_to_gateway_event(row: tuple) -> GatewayEvent:
    (
        gateway_event_id,
        tenant_id,
        client_slug,
        task_id,
        cf_aig_request_id,
        litellm_request_id,
        provider,
        model_route,
        provider_status,
        dlp_action,
        created_at,
    ) = row
    return GatewayEvent(
        gateway_event_id=gateway_event_id,
        tenant_id=tenant_id,
        client_slug=client_slug,
        task_id=task_id,
        cf_aig_request_id=cf_aig_request_id,
        litellm_request_id=litellm_request_id,
        provider=provider,
        model_route=model_route,
        provider_status=provider_status,
        dlp_action=dlp_action,
        created_at=created_at,
    )


_TASK_COLS = (
    "task_id, tenant_id, client_slug, entrypoint, session_id, requester, prompt, "
    "state, model_route_profile, result_summary, error, "
    "(SELECT value FROM task_metadata m WHERE m.task_id = tasks.task_id "
    "AND m.key = '__all__') AS metadata, created_at, updated_at"
)
_EVENT_COLS = "event_id, task_id, tenant_id, state, note, payload, created_at"
_TOOL_CALL_COLS = (
    "tool_call_id, task_id, tenant_id, tool_name, category, approval_required, "
    "status, parameters, result, requester_id, model_route, approval_record_id, "
    "integration_style, schema_validation, is_read, "
    "created_at"
)
_APPROVAL_COLS = (
    "approval_record_id, approval_request_id, task_id, tenant_id, tool_call_id, "
    "decision, approver_id, channel, payload_hash, decided_at, created_at"
)
_PROPOSAL_COLS = (
    "proposal_id, tenant_id, client_slug, task_id, session_id, agent_id, "
    "proposal_type, risk_level, status, title, rationale, proposed_patch, "
    "target_ref, evidence_pointers, patch_hash, approval_record_id, metadata, "
    "created_at, updated_at"
)
_EVALUATION_COLS = (
    "evaluation_id, proposal_id, tenant_id, passed, pending, checks, evaluator, "
    "summary, created_at"
)
_PROMOTION_COLS = (
    "promotion_id, proposal_id, tenant_id, client_slug, approval_record_id, "
    "evaluation_id, promoted_version, previous_version, patch_hash, "
    "ai_bom_snapshot_id, rolled_back, rollback_reason, promoted_by, created_at"
)
_AI_BOM_COLS = (
    "snapshot_id, tenant_id, client_slug, version, agents, tools, skills, "
    "prompts, model_routes, created_at"
)
_BUDGET_COLS = (
    "budget_event_id, tenant_id, client_slug, budget_owner, task_id, model, "
    "prompt_tokens, completion_tokens, estimated_cost_usd, created_at"
)
_GATEWAY_COLS = (
    "gateway_event_id, tenant_id, client_slug, task_id, cf_aig_request_id, "
    "litellm_request_id, provider, model_route, provider_status, dlp_action, "
    "created_at"
)


class RepositorySQL:
    """Postgres-backed repository over the existing 0001/0002 schema.

    One sync psycopg3 ``ConnectionPool``; each method borrows a connection via
    ``with self._pool.connection() as conn`` (which is also a single
    transaction). JSONB columns are adapted with ``psycopg.types.json.Jsonb``.
    Reads that span a task/proposal are tenant-scoped (DUR-02).
    """

    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 8) -> None:
        # Imported lazily so the in-memory POC stays importable without the
        # optional ``runtime`` dependency installed.
        from psycopg_pool import ConnectionPool

        # GOTCHA (Pitfall 1): pass connection options via kwargs, never appended
        # to the DSN string, or psycopg raises ProgrammingError at open.
        self._pool = ConnectionPool(
            conninfo=dsn, min_size=min_size, max_size=max_size, open=True
        )

    def close(self) -> None:
        """Close the pool. Used by tests to prove restart-survival across a
        fresh pool on the same DSN."""
        self._pool.close()

    # -- tasks --------------------------------------------------------------
    def create_task(self, task: TaskRecord) -> TaskRecord:
        from psycopg.types.json import Jsonb

        with self._pool.connection() as conn:
            # Upsert the task row.
            conn.execute(
                "INSERT INTO tasks (task_id, tenant_id, client_slug, entrypoint, "
                "session_id, requester_id, requester, prompt, state, "
                "model_route_profile, result_summary, error) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (task_id) DO UPDATE SET state=EXCLUDED.state, "
                "result_summary=EXCLUDED.result_summary, error=EXCLUDED.error, "
                "model_route_profile=EXCLUDED.model_route_profile, updated_at=now()",
                (
                    task.task_id,
                    task.tenant_id,
                    task.client_slug,
                    _enum_value(task.entrypoint),
                    task.session_id,
                    task.requester.requester_id,
                    Jsonb(task.requester.model_dump(mode="json")),
                    task.prompt,
                    _enum_value(task.state),
                    task.model_route_profile,
                    task.result_summary,
                    task.error,
                ),
            )
            # Pitfall 5: tasks has no metadata column. Persist non-empty metadata
            # into the separate task_metadata table under a single '__all__' key
            # so the dict round-trips (do NOT silently drop it).
            if task.metadata:
                conn.execute(
                    "INSERT INTO task_metadata (task_id, tenant_id, key, value) "
                    "VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (task_id, key) DO UPDATE SET value=EXCLUDED.value, "
                    "updated_at=now()",
                    (task.task_id, task.tenant_id, "__all__", Jsonb(task.metadata)),
                )
            # DUR-01: sessions must survive restart. Upsert the session row here
            # (no protocol change; TaskRecord carries everything sessions needs).
            conn.execute(
                "INSERT INTO sessions (session_id, tenant_id, client_slug, "
                "entrypoint, requester_id, active_task_id) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (session_id) DO UPDATE SET active_task_id=EXCLUDED.active_task_id, "
                "updated_at=now()",
                (
                    task.session_id,
                    task.tenant_id,
                    task.client_slug,
                    _enum_value(task.entrypoint),
                    task.requester.requester_id,
                    task.task_id,
                ),
            )
        return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_TASK_COLS} FROM tasks WHERE task_id = %s", (task_id,)
            ).fetchone()
        return _row_to_task(row) if row else None

    def transition_task(
        self, task_id: str, target: TaskState, note: str | None = None
    ) -> TaskRecord:
        from uuid import uuid4

        current = self.get_task(task_id)
        if current is None:
            raise KeyError(task_id)
        assert_transition(current.state, target)
        # Coerce a bare TaskState enum to its string value (Pitfall 6): str() on a
        # str-mixin enum yields 'TaskState.RUNNING', so use .value when available.
        target_value = _enum_value(target)
        current_value = _enum_value(current.state)
        # Single transaction: conditionally UPDATE the state AND append the audit
        # event atomically (Pitfall 7) so a crash cannot advance state without the
        # audit row. The UPDATE is GUARDED on the state we validated the transition
        # from (WR-02): if a concurrent caller already advanced the task out of that
        # state, the UPDATE matches no row and we raise ConcurrentModification rather
        # than double-advancing and writing a duplicate audit event.
        with self._pool.connection() as conn:
            updated = conn.execute(
                "UPDATE tasks SET state=%s, updated_at=now() "
                "WHERE task_id=%s AND state=%s",
                (target_value, task_id, current_value),
            ).rowcount
            if not updated:
                raise ConcurrentModification(
                    f"task {task_id} was not in state {current_value!r} at update "
                    "time; transition lost the race"
                )
            conn.execute(
                "INSERT INTO task_events (event_id, task_id, tenant_id, state, note) "
                "VALUES (%s,%s,%s,%s,%s)",
                (uuid4().hex, task_id, current.tenant_id, target_value, note),
            )
        result = self.get_task(task_id)
        assert result is not None
        return result

    def append_event(self, event: TaskEvent) -> TaskEvent:
        from psycopg.types.json import Jsonb

        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO task_events (event_id, task_id, tenant_id, state, "
                "note, payload, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (event_id) DO NOTHING",
                (
                    event.event_id,
                    event.task_id,
                    event.tenant_id,
                    _enum_value(event.state),
                    event.note,
                    Jsonb(event.payload),
                    event.created_at,
                ),
            )
        return event

    def list_events(self, task_id: str, tenant_id: str) -> list[TaskEvent]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_EVENT_COLS} FROM task_events "
                "WHERE task_id = %s AND tenant_id = %s ORDER BY created_at",
                (task_id, tenant_id),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    # -- tool calls ---------------------------------------------------------
    def upsert_tool_call(self, call: ToolCall) -> ToolCall:
        from psycopg.types.json import Jsonb

        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO tool_calls (tool_call_id, task_id, tenant_id, "
                "tool_name, category, approval_required, status, parameters, "
                "result, requester_id, model_route, approval_record_id, "
                "integration_style, schema_validation, is_read, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (tool_call_id) DO UPDATE SET status=EXCLUDED.status, "
                "parameters=EXCLUDED.parameters, result=EXCLUDED.result, "
                "approval_record_id=EXCLUDED.approval_record_id, "
                "model_route=EXCLUDED.model_route, "
                "integration_style=EXCLUDED.integration_style, "
                "schema_validation=EXCLUDED.schema_validation, "
                "is_read=EXCLUDED.is_read",
                (
                    call.tool_call_id,
                    call.task_id,
                    call.tenant_id,
                    call.tool_name,
                    _enum_value(call.category),
                    call.approval_required,
                    _enum_value(call.status),
                    Jsonb(call.parameters),
                    Jsonb(call.result) if call.result is not None else None,
                    call.requester_id,
                    call.model_route,
                    call.approval_record_id,
                    call.integration_style,
                    call.schema_validation,
                    call.is_read,
                    call.created_at,
                ),
            )
        return call

    def get_tool_call(self, tool_call_id: str) -> ToolCall | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_TOOL_CALL_COLS} FROM tool_calls WHERE tool_call_id = %s",
                (tool_call_id,),
            ).fetchone()
        return _row_to_tool_call(row) if row else None

    def list_tool_calls(self, task_id: str, tenant_id: str) -> list[ToolCall]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_TOOL_CALL_COLS} FROM tool_calls "
                "WHERE task_id = %s AND tenant_id = %s ORDER BY created_at",
                (task_id, tenant_id),
            ).fetchall()
        return [_row_to_tool_call(r) for r in rows]

    # -- approvals ----------------------------------------------------------
    def upsert_approval(self, record: ApprovalRecord) -> ApprovalRecord:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO approval_records (approval_record_id, "
                "approval_request_id, task_id, tenant_id, tool_call_id, decision, "
                "approver_id, channel, payload_hash, decided_at, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (approval_record_id) DO UPDATE SET "
                "decision=EXCLUDED.decision, approver_id=EXCLUDED.approver_id, "
                "channel=EXCLUDED.channel, decided_at=EXCLUDED.decided_at",
                (
                    record.approval_record_id,
                    record.approval_request_id,
                    record.task_id,
                    record.tenant_id,
                    record.tool_call_id,
                    _enum_value(record.decision),
                    record.approver_id,
                    record.channel,
                    record.payload_hash,
                    record.decided_at,
                    record.created_at,
                ),
            )
        return record

    def get_approval(self, approval_record_id: str) -> ApprovalRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_APPROVAL_COLS} FROM approval_records "
                "WHERE approval_record_id = %s",
                (approval_record_id,),
            ).fetchone()
        return _row_to_approval(row) if row else None

    def list_approvals(self, task_id: str, tenant_id: str) -> list[ApprovalRecord]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_APPROVAL_COLS} FROM approval_records "
                "WHERE task_id = %s AND tenant_id = %s ORDER BY created_at",
                (task_id, tenant_id),
            ).fetchall()
        return [_row_to_approval(r) for r in rows]

    # -- self-improvement proposals ----------------------------------------
    def upsert_proposal(
        self, proposal: SelfImprovementProposal
    ) -> SelfImprovementProposal:
        from psycopg.types.json import Jsonb

        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO self_improvement_proposals (proposal_id, tenant_id, "
                "client_slug, task_id, session_id, agent_id, proposal_type, "
                "risk_level, status, title, rationale, proposed_patch, target_ref, "
                "evidence_pointers, patch_hash, approval_record_id, metadata, "
                "created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (proposal_id) DO UPDATE SET status=EXCLUDED.status, "
                "patch_hash=EXCLUDED.patch_hash, "
                "approval_record_id=EXCLUDED.approval_record_id, "
                "metadata=EXCLUDED.metadata, updated_at=now()",
                (
                    proposal.proposal_id,
                    proposal.tenant_id,
                    proposal.client_slug,
                    proposal.task_id,
                    proposal.session_id,
                    proposal.agent_id,
                    _enum_value(proposal.proposal_type),
                    _enum_value(proposal.risk_level),
                    _enum_value(proposal.status),
                    proposal.title,
                    proposal.rationale,
                    proposal.proposed_patch,
                    proposal.target_ref,
                    Jsonb(proposal.evidence_pointers),
                    proposal.patch_hash,
                    proposal.approval_record_id,
                    Jsonb(proposal.metadata),
                    proposal.created_at,
                    proposal.updated_at,
                ),
            )
        return proposal

    def get_proposal(self, proposal_id: str) -> SelfImprovementProposal | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_PROPOSAL_COLS} FROM self_improvement_proposals "
                "WHERE proposal_id = %s",
                (proposal_id,),
            ).fetchone()
        return _row_to_proposal(row) if row else None

    def upsert_evaluation(self, evaluation: EvaluationResult) -> EvaluationResult:
        from psycopg.types.json import Jsonb

        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO self_improvement_evaluations (evaluation_id, "
                "proposal_id, tenant_id, passed, pending, checks, evaluator, "
                "summary, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (evaluation_id) DO UPDATE SET passed=EXCLUDED.passed, "
                "pending=EXCLUDED.pending, checks=EXCLUDED.checks, "
                "summary=EXCLUDED.summary",
                (
                    evaluation.evaluation_id,
                    evaluation.proposal_id,
                    evaluation.tenant_id,
                    evaluation.passed,
                    evaluation.pending,
                    Jsonb(evaluation.checks),
                    evaluation.evaluator,
                    evaluation.summary,
                    evaluation.created_at,
                ),
            )
        return evaluation

    def get_evaluation(self, evaluation_id: str) -> EvaluationResult | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_EVALUATION_COLS} FROM self_improvement_evaluations "
                "WHERE evaluation_id = %s",
                (evaluation_id,),
            ).fetchone()
        return _row_to_evaluation(row) if row else None

    def list_evaluations(
        self, proposal_id: str, tenant_id: str
    ) -> list[EvaluationResult]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_EVALUATION_COLS} FROM self_improvement_evaluations "
                "WHERE proposal_id = %s AND tenant_id = %s ORDER BY created_at",
                (proposal_id, tenant_id),
            ).fetchall()
        return [_row_to_evaluation(r) for r in rows]

    def upsert_promotion(self, promotion: PromotionRecord) -> PromotionRecord:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO self_improvement_promotions (promotion_id, "
                "proposal_id, tenant_id, client_slug, approval_record_id, "
                "evaluation_id, promoted_version, previous_version, patch_hash, "
                "ai_bom_snapshot_id, rolled_back, rollback_reason, promoted_by, "
                "created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (promotion_id) DO UPDATE SET "
                "rolled_back=EXCLUDED.rolled_back, "
                "rollback_reason=EXCLUDED.rollback_reason, "
                "ai_bom_snapshot_id=EXCLUDED.ai_bom_snapshot_id",
                (
                    promotion.promotion_id,
                    promotion.proposal_id,
                    promotion.tenant_id,
                    promotion.client_slug,
                    promotion.approval_record_id,
                    promotion.evaluation_id,
                    promotion.promoted_version,
                    promotion.previous_version,
                    promotion.patch_hash,
                    promotion.ai_bom_snapshot_id,
                    promotion.rolled_back,
                    promotion.rollback_reason,
                    promotion.promoted_by,
                    promotion.created_at,
                ),
            )
        return promotion

    def get_promotion(self, promotion_id: str) -> PromotionRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_PROMOTION_COLS} FROM self_improvement_promotions "
                "WHERE promotion_id = %s",
                (promotion_id,),
            ).fetchone()
        return _row_to_promotion(row) if row else None

    # -- active-version pointer (SI-02b) + AI-BOM persistence (SI-02) -------
    def current_active_version(self, tenant_id: str) -> str | None:
        # Tenant-scoped read (DUR-02): never another tenant's pointer.
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT active_version FROM self_improvement_active_version "
                "WHERE tenant_id = %s",
                (tenant_id,),
            ).fetchone()
        return row[0] if row else None

    def set_active_version(
        self, tenant_id: str, version: str, promotion_id: str | None = None
    ) -> None:
        # Upsert the per-tenant pointer (mirrors the upsert_promotion shape).
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO self_improvement_active_version "
                "(tenant_id, active_version, promotion_id, updated_at) "
                "VALUES (%s,%s,%s,now()) "
                "ON CONFLICT (tenant_id) DO UPDATE SET "
                "active_version=EXCLUDED.active_version, "
                "promotion_id=EXCLUDED.promotion_id, updated_at=now()",
                (tenant_id, version, promotion_id),
            )

    def upsert_ai_bom(self, snapshot: AIBOMSnapshot) -> AIBOMSnapshot:
        from psycopg.types.json import Jsonb

        # Serialize once and reuse (WR-03): five separate model_dump(mode="json")
        # calls re-serialize the whole model each time, and any per-call datetime
        # coercion variance could persist slightly different JSONB across the
        # columns of a single snapshot row. One dump guarantees consistency.
        dumped = snapshot.model_dump(mode="json")
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO ai_bom_snapshots (snapshot_id, tenant_id, "
                "client_slug, version, agents, tools, skills, prompts, "
                "model_routes, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (snapshot_id) DO NOTHING",
                (
                    snapshot.snapshot_id,
                    snapshot.tenant_id,
                    snapshot.client_slug,
                    snapshot.version,
                    Jsonb(dumped["agents"]),
                    Jsonb(dumped["tools"]),
                    Jsonb(dumped["skills"]),
                    Jsonb(dumped["prompts"]),
                    Jsonb(dumped["model_routes"]),
                    snapshot.created_at,
                ),
            )
        return snapshot

    def get_ai_bom(self, snapshot_id: str, tenant_id: str) -> AIBOMSnapshot | None:
        # Tenant-scoped read (DUR-02): a tenant mismatch returns None.
        with self._pool.connection() as conn:
            row = conn.execute(
                f"SELECT {_AI_BOM_COLS} FROM ai_bom_snapshots "
                "WHERE snapshot_id = %s AND tenant_id = %s",
                (snapshot_id, tenant_id),
            ).fetchone()
        return _row_to_ai_bom(row) if row else None

    # -- budget ledger + gateway events (GW-01 / D-04 / DUR-02) -------------
    def record_budget_event(self, event: BudgetEvent) -> BudgetEvent:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO budget_ledger (budget_event_id, tenant_id, "
                "client_slug, budget_owner, task_id, model, prompt_tokens, "
                "completion_tokens, estimated_cost_usd, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (budget_event_id) DO NOTHING",
                (
                    event.budget_event_id,
                    event.tenant_id,
                    event.client_slug,
                    event.budget_owner,
                    event.task_id,
                    event.model,
                    event.prompt_tokens,
                    event.completion_tokens,
                    event.estimated_cost_usd,
                    event.created_at,
                ),
            )
        return event

    def budget_month_to_date(
        self, tenant_id: str, budget_owner: str, since: datetime
    ) -> float:
        # Tenant-scoped aggregate over the idx_budget_owner_month index (DUR-02).
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM budget_ledger "
                "WHERE tenant_id=%s AND budget_owner=%s AND created_at>=%s",
                (tenant_id, budget_owner, since),
            ).fetchone()
        return float(row[0]) if row else 0.0

    def record_gateway_event(self, event: GatewayEvent) -> GatewayEvent:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO gateway_events (gateway_event_id, tenant_id, "
                "client_slug, task_id, cf_aig_request_id, litellm_request_id, "
                "provider, model_route, provider_status, dlp_action, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (gateway_event_id) DO NOTHING",
                (
                    event.gateway_event_id,
                    event.tenant_id,
                    event.client_slug,
                    event.task_id,
                    event.cf_aig_request_id,
                    event.litellm_request_id,
                    event.provider,
                    event.model_route,
                    event.provider_status,
                    event.dlp_action,
                    event.created_at,
                ),
            )
        return event

    def list_gateway_events(self, task_id: str, tenant_id: str) -> list[GatewayEvent]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_GATEWAY_COLS} FROM gateway_events "
                "WHERE task_id = %s AND tenant_id = %s ORDER BY created_at",
                (task_id, tenant_id),
            ).fetchall()
        return [_row_to_gateway_event(r) for r in rows]


_SINGLETON: Repository | None = None


def get_repository() -> Repository:
    """Return the active repository (process-wide singleton).

    When ``DATABASE_URL`` is set we return a durable ``RepositorySQL`` (DUR-01)
    so ingress and the worker share durable Postgres-backed state that survives
    restart. When unset we fall back to the in-memory singleton so the POC stays
    importable and testable without a database.
    """
    global _SINGLETON
    if _SINGLETON is None:
        from agent_mesh.settings import get_settings

        database_url = get_settings().database_url
        if database_url:
            _SINGLETON = RepositorySQL(database_url)
        else:
            _SINGLETON = InMemoryRepository()
    return _SINGLETON
