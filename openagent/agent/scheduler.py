"""Scheduled tasks: lightweight, local, cron-like task definitions.

This module stores task definitions and decides *when* a task is due; it
deliberately does not run its own daemon/background process -- invoke
`openagent schedule tick` from cron, systemd timers, or Windows Task
Scheduler, keeping the local footprint minimal (no persistent low-RAM
background process required by the harness itself).
"""
from __future__ import annotations

import dataclasses
import json
import time
import uuid
from pathlib import Path
from typing import Callable, Optional


@dataclasses.dataclass
class ScheduledTask:
    id: str
    name: str
    interval_seconds: float
    action: str              # e.g. "skill:research-citations" or "shell:pytest -q"
    last_run_at: float | None = None
    next_run_at: float = dataclasses.field(default_factory=time.time)
    enabled: bool = True

    def is_due(self, now: float | None = None) -> bool:
        return self.enabled and (now or time.time()) >= self.next_run_at

    def mark_ran(self, now: float | None = None) -> None:
        now = now or time.time()
        self.last_run_at = now
        self.next_run_at = now + self.interval_seconds


class SchedulerStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8") or "[]")

    def _save(self, tasks: list[dict]) -> None:
        self.path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")

    def add(self, name: str, interval_seconds: float, action: str) -> ScheduledTask:
        tasks = self._load()
        task = ScheduledTask(id=str(uuid.uuid4())[:8], name=name,
                              interval_seconds=interval_seconds, action=action)
        tasks.append(dataclasses.asdict(task))
        self._save(tasks)
        return task

    def list(self) -> list[ScheduledTask]:
        return [ScheduledTask(**t) for t in self._load()]

    def due(self, now: float | None = None) -> list[ScheduledTask]:
        return [t for t in self.list() if t.is_due(now)]

    def mark_ran(self, task_id: str, now: float | None = None) -> None:
        tasks = self._load()
        for t in tasks:
            if t["id"] == task_id:
                now = now or time.time()
                t["last_run_at"] = now
                t["next_run_at"] = now + t["interval_seconds"]
        self._save(tasks)

    def remove(self, task_id: str) -> bool:
        tasks = self._load()
        new_tasks = [t for t in tasks if t["id"] != task_id]
        self._save(new_tasks)
        return len(new_tasks) != len(tasks)


def tick(store: SchedulerStore, runner: Callable[[ScheduledTask], dict], now: Optional[float] = None) -> list[dict]:
    """Run every due task once via `runner`, then reschedule it."""
    results = []
    for task in store.due(now):
        outcome = runner(task)
        store.mark_ran(task.id, now)
        results.append({"task_id": task.id, "name": task.name, "outcome": outcome})
    return results
