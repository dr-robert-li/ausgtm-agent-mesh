"""Evaluator + Contract Validator records, embedded on Task.evaluations[]."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class EvaluationKind(str, Enum):
    evaluator = "evaluator"  # semantic / meaning
    validator = "validator"  # structural / shape


class EvaluationVerdict(str, Enum):
    pass_ = "pass"
    warn = "warn"
    fail = "fail"


class EvaluationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: EvaluationKind
    verdict: EvaluationVerdict
    score: float | None = None
    rubric: str | None = None
    rationale: str | None = None
    evaluator_model_tier: str | None = None  # 'L' mandatory for evaluator
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
