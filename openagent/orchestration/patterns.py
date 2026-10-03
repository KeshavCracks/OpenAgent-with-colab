"""Harness-engineering orchestration patterns: planner/worker/reviewer with
contracts, retries, budgets, checkpoints, and rollback.

This intentionally stays framework-agnostic (plain dataclasses + callables)
so it can drive either the local agent loop or a plain Python script.
"""
from __future__ import annotations

import dataclasses
import time
from typing import Any, Callable, Optional

from openagent.orchestration.budgets import Budget, BudgetExceededError


@dataclasses.dataclass
class StepContract:
    name: str
    action: Callable[[], Any]
    preconditions: list[Callable[[], bool]] = dataclasses.field(default_factory=list)
    postconditions: list[Callable[[Any], bool]] = dataclasses.field(default_factory=list)
    max_retries: int = 2


@dataclasses.dataclass
class StepResult:
    name: str
    ok: bool
    attempts: int
    output: Any = None
    error: str | None = None
    duration_seconds: float = 0.0


class PlannerWorkerReviewer:
    def __init__(
        self,
        budget: Optional[Budget] = None,
        on_checkpoint: Optional[Callable[[StepResult], None]] = None,
        on_rollback: Optional[Callable[[StepResult], None]] = None,
    ):
        self.budget = budget or Budget()
        self.on_checkpoint = on_checkpoint
        self.on_rollback = on_rollback
        self.history: list[StepResult] = []

    def run_step(self, contract: StepContract) -> StepResult:
        started = time.time()
        for precond in contract.preconditions:
            if not precond():
                result = StepResult(contract.name, ok=False, attempts=0,
                                     error="precondition failed", duration_seconds=0.0)
                self.history.append(result)
                return result

        last_error: str | None = None
        for attempt in range(1, contract.max_retries + 2):
            self.budget.check_wall_clock()
            try:
                output = contract.action()
                postconditions_ok = all(p(output) for p in contract.postconditions)
                if not postconditions_ok:
                    raise AssertionError("postcondition failed")
                result = StepResult(
                    contract.name, ok=True, attempts=attempt, output=output,
                    duration_seconds=time.time() - started,
                )
                self.history.append(result)
                if self.on_checkpoint:
                    self.on_checkpoint(result)
                return result
            except BudgetExceededError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue

        result = StepResult(contract.name, ok=False, attempts=contract.max_retries + 1,
                             error=last_error, duration_seconds=time.time() - started)
        self.history.append(result)
        if self.on_rollback:
            self.on_rollback(result)
        return result

    def run_plan(self, steps: list[StepContract], stop_on_failure: bool = True) -> list[StepResult]:
        results = []
        for step in steps:
            result = self.run_step(step)
            results.append(result)
            if not result.ok and stop_on_failure:
                break
        return results
