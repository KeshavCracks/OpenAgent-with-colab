"""Trajectory recording and inspection.

A trajectory is an append-only JSONL file of structured events for one
session: model turns, tool calls (with full arguments/results/timings),
phase switches, and summarization events. This is the primary artifact for
"trajectory inspection" and "tool-call details" in the harness UI/CLI.
"""
from __future__ import annotations

import dataclasses
import json
import time
import uuid
from pathlib import Path
from typing import Any, Iterator


@dataclasses.dataclass
class TrajectoryEvent:
    event_id: str
    session_id: str
    type: str          # "message" | "tool_call" | "phase_switch" | "summarization" | "error"
    t: float
    data: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self))


class TrajectoryRecorder:
    def __init__(self, path: Path | str, session_id: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id

    def record(self, event_type: str, data: dict) -> TrajectoryEvent:
        event = TrajectoryEvent(
            event_id=str(uuid.uuid4()), session_id=self.session_id,
            type=event_type, t=time.time(), data=data,
        )
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(event.to_json() + "\n")
        return event

    def record_message(self, role: str, content: Any) -> TrajectoryEvent:
        return self.record("message", {"role": role, "content": content})

    def record_tool_call(self, tool: str, arguments: dict, result: Any, ok: bool,
                          duration_ms: float, error: str | None = None) -> TrajectoryEvent:
        return self.record("tool_call", {
            "tool": tool, "arguments": arguments, "result": result,
            "ok": ok, "duration_ms": duration_ms, "error": error,
        })

    def record_phase_switch(self, phase: str, model_id: str) -> TrajectoryEvent:
        return self.record("phase_switch", {"phase": phase, "model_id": model_id})


def read_trajectory(path: Path | str) -> list[TrajectoryEvent]:
    path = Path(path)
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        events.append(TrajectoryEvent(**raw))
    return events


def summarize_trajectory(events: list[TrajectoryEvent]) -> dict:
    tool_calls = [e for e in events if e.type == "tool_call"]
    messages = [e for e in events if e.type == "message"]
    errors = [e for e in tool_calls if not e.data.get("ok", True)]
    by_tool: dict[str, int] = {}
    total_duration_ms = 0.0
    for e in tool_calls:
        by_tool[e.data["tool"]] = by_tool.get(e.data["tool"], 0) + 1
        total_duration_ms += e.data.get("duration_ms", 0.0)
    return {
        "total_events": len(events),
        "message_count": len(messages),
        "tool_call_count": len(tool_calls),
        "tool_call_errors": len(errors),
        "tool_call_breakdown": by_tool,
        "total_tool_duration_ms": round(total_duration_ms, 2),
        "phase_switches": [e.data for e in events if e.type == "phase_switch"],
    }


def iter_tool_call_details(events: list[TrajectoryEvent]) -> Iterator[dict]:
    for e in events:
        if e.type == "tool_call":
            yield {"event_id": e.event_id, "t": e.t, **e.data}
