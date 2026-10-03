"""Budgets: bound a task's tool calls, wall-clock time, and tokens so a
runaway plan fails fast and visibly rather than silently burning quota."""
from __future__ import annotations

import dataclasses
import time


class BudgetExceededError(RuntimeError):
    pass


@dataclasses.dataclass
class Budget:
    max_tool_calls: int = 50
    max_wall_seconds: float = 1800.0
    max_tokens: int = 200_000
    _started_at: float = dataclasses.field(default_factory=time.time, repr=False)
    _tool_calls_used: int = 0
    _tokens_used: int = 0

    def record_tool_call(self) -> None:
        self._tool_calls_used += 1
        if self._tool_calls_used > self.max_tool_calls:
            raise BudgetExceededError(f"tool call budget exceeded ({self.max_tool_calls})")

    def record_tokens(self, n: int) -> None:
        self._tokens_used += n
        if self._tokens_used > self.max_tokens:
            raise BudgetExceededError(f"token budget exceeded ({self.max_tokens})")

    def check_wall_clock(self) -> None:
        elapsed = time.time() - self._started_at
        if elapsed > self.max_wall_seconds:
            raise BudgetExceededError(f"wall-clock budget exceeded ({self.max_wall_seconds}s)")

    def remaining(self) -> dict:
        return {
            "tool_calls_remaining": max(0, self.max_tool_calls - self._tool_calls_used),
            "tokens_remaining": max(0, self.max_tokens - self._tokens_used),
            "seconds_remaining": max(0.0, self.max_wall_seconds - (time.time() - self._started_at)),
        }
