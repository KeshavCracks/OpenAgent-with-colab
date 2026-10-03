"""Benchmark harness: smoke, tool-use, multi-file coding, research, and
browser task categories, runnable against any configured model/backend so
results are comparable across the model registry.

Tasks are plain callables returning a BenchmarkResult so they can run with
zero network access (unit-test friendly) or against a real endpoint when one
is available -- the harness doesn't care which, it just records results
tagged with the `model_id` the caller says it used.
"""
from __future__ import annotations

import dataclasses
import time
import traceback
from typing import Any, Callable


@dataclasses.dataclass
class BenchmarkResult:
    task_name: str
    category: str
    passed: bool
    duration_seconds: float
    detail: str = ""
    metrics: dict[str, Any] = dataclasses.field(default_factory=dict)


TaskFn = Callable[[], BenchmarkResult]


@dataclasses.dataclass
class BenchmarkTask:
    name: str
    category: str   # smoke | tool_use | multi_file_coding | research | browser
    fn: TaskFn


class BenchmarkHarness:
    def __init__(self):
        self.tasks: list[BenchmarkTask] = []

    def register(self, task: BenchmarkTask) -> None:
        self.tasks.append(task)

    def run_all(self, model_id: str = "unspecified") -> list[dict]:
        results = []
        for task in self.tasks:
            started = time.time()
            try:
                result = task.fn()
            except Exception as exc:  # noqa: BLE001
                result = BenchmarkResult(
                    task_name=task.name, category=task.category, passed=False,
                    duration_seconds=time.time() - started,
                    detail=f"{exc}\n{traceback.format_exc(limit=3)}",
                )
            results.append({"model_id": model_id, **dataclasses.asdict(result)})
        return results

    def compare(self, results_by_model: dict[str, list[dict]]) -> dict:
        """Aggregate pass rate per model for a cross-model comparison report."""
        report = {}
        for model_id, results in results_by_model.items():
            total = len(results)
            passed = sum(1 for r in results if r["passed"])
            report[model_id] = {
                "total": total,
                "passed": passed,
                "pass_rate": round(passed / total, 3) if total else 0.0,
                "by_category": _by_category(results),
            }
        return report


def _by_category(results: list[dict]) -> dict:
    cats: dict[str, dict] = {}
    for r in results:
        cat = cats.setdefault(r["category"], {"total": 0, "passed": 0})
        cat["total"] += 1
        cat["passed"] += int(r["passed"])
    return cats
