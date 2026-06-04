"""Per-user monthly model budget tracking.

LiteLLM is the enforcement point in production (it can hard-stop a request). This
module is the durable ledger + a local check the worker uses to halt a run when a
budget owner exceeds their configured monthly cap (default USD 50).
"""

from __future__ import annotations

from collections import defaultdict
from threading import RLock

from agent_mesh.contracts.models import BudgetEvent


class BudgetExceeded(RuntimeError):
    """Raised when a model call would exceed the budget owner's monthly cap."""


class BudgetTracker:
    def __init__(self, monthly_cap_usd: float = 50.0) -> None:
        self._cap = monthly_cap_usd
        self._spent: dict[str, float] = defaultdict(float)
        self._events: list[BudgetEvent] = []
        self._lock = RLock()

    def month_to_date(self, budget_owner: str) -> float:
        with self._lock:
            return self._spent[budget_owner]

    def check(self, budget_owner: str, incremental_usd: float) -> None:
        with self._lock:
            if self._spent[budget_owner] + incremental_usd > self._cap:
                raise BudgetExceeded(
                    f"budget owner {budget_owner!r} would exceed cap "
                    f"${self._cap:.2f} (spent ${self._spent[budget_owner]:.4f})"
                )

    def record(self, event: BudgetEvent) -> BudgetEvent:
        with self._lock:
            self._spent[event.budget_owner] += event.estimated_cost_usd
            self._events.append(event)
            return event
