"""The core local agent loop (ReAct-style: plan -> tool call -> observe -> repeat).

Runs entirely on the local, low-RAM harness process. The only network call
is the chat-completions request to the remote llama-server; everything else
(tool dispatch, context budgeting, trajectory recording) happens locally.
"""
from __future__ import annotations

import dataclasses
import json
import time
from typing import Any, Optional, Protocol

from openagent.agent.context import ContextManager
from openagent.agent.llm_client import ChatResponse, LlamaCppClient
from openagent.agent.trajectory import TrajectoryRecorder


class ToolRegistryProtocol(Protocol):
    def schemas(self) -> list[dict]: ...
    def dispatch(self, name: str, arguments: dict) -> Any: ...


class MaxIterationsExceeded(RuntimeError):
    pass


class WallClockExceeded(RuntimeError):
    pass


@dataclasses.dataclass
class LoopResult:
    final_message: str
    messages: list[dict]
    tool_call_count: int
    iterations: int
    stopped_reason: str


def _safe_json_loads(s: str) -> dict:
    try:
        return json.loads(s) if s else {}
    except json.JSONDecodeError:
        return {}


class AgentLoop:
    def __init__(
        self,
        llm_client: LlamaCppClient,
        tool_registry: ToolRegistryProtocol,
        context_manager: ContextManager,
        recorder: Optional[TrajectoryRecorder] = None,
        system_prompt: str = "You are OpenAgent, a careful local coding/research agent.",
    ):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.context_manager = context_manager
        self.recorder = recorder
        self.system_prompt = system_prompt

    def _record_message(self, role: str, content: Any) -> None:
        if self.recorder:
            self.recorder.record_message(role, content)

    def _record_tool_call(self, tool: str, arguments: dict, result: Any, ok: bool,
                           duration_ms: float, error: str | None) -> None:
        if self.recorder:
            self.recorder.record_tool_call(tool, arguments, result, ok, duration_ms, error)

    def run(
        self,
        task: str,
        messages: Optional[list[dict]] = None,
        max_iterations: int = 20,
        max_wall_seconds: float = 600.0,
        max_tool_calls: int | None = None,
    ) -> LoopResult:
        started = time.time()
        if messages is None:
            messages = [{"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": task}]
            self._record_message("system", self.system_prompt)
            self._record_message("user", task)

        tool_call_count = 0
        stopped_reason = "completed"

        for iteration in range(1, max_iterations + 1):
            if time.time() - started > max_wall_seconds:
                stopped_reason = "wall_clock_exceeded"
                break
            if max_tool_calls is not None and tool_call_count >= max_tool_calls:
                stopped_reason = "max_tool_calls_exceeded"
                break

            messages = self.context_manager.maybe_compact(messages)
            response: ChatResponse = self.llm_client.chat(messages, tools=self.tool_registry.schemas())

            assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content}
            if response.tool_calls:
                assistant_msg["tool_calls"] = response.tool_calls
            messages.append(assistant_msg)
            self._record_message("assistant", response.content)

            if not response.tool_calls:
                stopped_reason = "completed"
                return LoopResult(
                    final_message=response.content or "",
                    messages=messages, tool_call_count=tool_call_count,
                    iterations=iteration, stopped_reason=stopped_reason,
                )

            for tc in response.tool_calls:
                if max_tool_calls is not None and tool_call_count >= max_tool_calls:
                    break
                fn = tc.get("function", {})
                name = fn.get("name", "")
                arguments = _safe_json_loads(fn.get("arguments", "{}"))
                call_started = time.time()
                try:
                    result = self.tool_registry.dispatch(name, arguments)
                    ok, error = getattr(result, "ok", True), getattr(result, "error", None)
                    payload = getattr(result, "result", result)
                except Exception as exc:  # noqa: BLE001
                    ok, error, payload = False, str(exc), None
                duration_ms = (time.time() - call_started) * 1000
                tool_call_count += 1
                self._record_tool_call(name, arguments, payload, ok, duration_ms, error)
                tool_message = {
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{tool_call_count}"),
                    "name": name,
                    "content": json.dumps(payload if ok else {"error": error}),
                }
                messages.append(tool_message)

        else:
            stopped_reason = "max_iterations_exceeded"

        last_assistant = next((m for m in reversed(messages) if m.get("role") == "assistant"), None)
        return LoopResult(
            final_message=(last_assistant or {}).get("content") or "",
            messages=messages, tool_call_count=tool_call_count,
            iterations=max_iterations, stopped_reason=stopped_reason,
        )
