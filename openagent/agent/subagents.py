"""Subagents: spawn an isolated child session with a restricted tool/permission
set for a bounded subtask (e.g. "research this API" or "run the test suite
and summarize failures"), reporting results back to the parent trajectory.
"""
from __future__ import annotations

import dataclasses
import time
from typing import Callable, Optional

from openagent.agent.session import SessionMeta, SessionStore
from openagent.agent.trajectory import TrajectoryRecorder
from openagent.tools.base import ToolRegistry


@dataclasses.dataclass
class SubagentSpec:
    name: str
    task: str
    allowed_tools: tuple[str, ...]
    max_tool_calls: int = 20
    max_wall_seconds: float = 600.0


@dataclasses.dataclass
class SubagentResult:
    session_id: str
    ok: bool
    summary: str
    tool_call_count: int
    duration_seconds: float


class RestrictedToolRegistry:
    """Wraps a ToolRegistry, exposing only an allow-listed subset."""

    def __init__(self, base: ToolRegistry, allowed_tools: tuple[str, ...]):
        self._base = base
        self._allowed = set(allowed_tools)

    def names(self) -> list[str]:
        return [n for n in self._base.names() if n in self._allowed]

    def schemas(self) -> list[dict]:
        return [s for s in self._base.schemas() if s["function"]["name"] in self._allowed]

    def dispatch(self, name: str, arguments: dict):
        if name not in self._allowed:
            raise PermissionError(f"Subagent is not permitted to use tool '{name}'")
        return self._base.dispatch(name, arguments)


class SubagentManager:
    def __init__(self, sessions: SessionStore, trajectories_dir: str,
                 run_agent_loop: Optional[Callable] = None):
        self.sessions = sessions
        self.trajectories_dir = trajectories_dir
        self._run_agent_loop = run_agent_loop  # injected to avoid circular import w/ loop.py

    def spawn(self, parent_session_id: str, spec: SubagentSpec, tool_registry: ToolRegistry,
               agent_loop_fn: Callable) -> SubagentResult:
        child = self.sessions.create(
            workspace=self.sessions.load(parent_session_id).workspace,
            parent_session_id=parent_session_id,
        )
        restricted = RestrictedToolRegistry(tool_registry, spec.allowed_tools)
        recorder = TrajectoryRecorder(f"{self.trajectories_dir}/{child.session_id}.jsonl", child.session_id)
        recorder.record("phase_switch", {"phase": "subagent_start", "spec": dataclasses.asdict(spec)})

        started = time.time()
        try:
            result = agent_loop_fn(
                task=spec.task, tool_registry=restricted, recorder=recorder,
                max_tool_calls=spec.max_tool_calls, max_wall_seconds=spec.max_wall_seconds,
            )
            ok = True
            summary = result.get("final_message", "") if isinstance(result, dict) else str(result)
            tool_call_count = result.get("tool_call_count", 0) if isinstance(result, dict) else 0
        except Exception as exc:  # noqa: BLE001
            ok = False
            summary = f"subagent failed: {exc}"
            tool_call_count = 0

        duration = time.time() - started
        child.status = "stopped" if ok else "failed"
        self.sessions.save(child)
        recorder.record("phase_switch", {"phase": "subagent_end", "ok": ok})
        return SubagentResult(
            session_id=child.session_id, ok=ok, summary=summary,
            tool_call_count=tool_call_count, duration_seconds=duration,
        )
