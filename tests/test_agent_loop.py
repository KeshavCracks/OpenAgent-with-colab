import json
from pathlib import Path

from openagent.agent.builtin_tools import build_default_tool_registry
from openagent.agent.context import ContextBudget, ContextManager
from openagent.agent.llm_client import LlamaCppClient
from openagent.agent.loop import AgentLoop
from openagent.agent.trajectory import TrajectoryRecorder, read_trajectory, summarize_trajectory
from openagent.tools.base import WorkspaceGuard


def _make_loop(tmp_path, transport, recorder=None):
    guard = WorkspaceGuard(root=tmp_path)
    registry = build_default_tool_registry(guard)
    client = LlamaCppClient(transport=transport)
    ctx = ContextManager(ContextBudget())
    return AgentLoop(client, registry, ctx, recorder=recorder)


def test_single_step_no_tool_call(tmp_path):
    def transport(url, headers, body):
        return {"choices": [{"message": {"role": "assistant", "content": "just an answer"},
                              "finish_reason": "stop"}]}

    loop = _make_loop(tmp_path, transport)
    result = loop.run("say hi")
    assert result.final_message == "just an answer"
    assert result.tool_call_count == 0
    assert result.stopped_reason == "completed"


def test_multi_step_tool_call_then_final_answer(tmp_path):
    (tmp_path / "data.txt").write_text("42\n", encoding="utf-8")
    calls = {"n": 0}

    def transport(url, headers, body):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "read", "arguments": json.dumps({"path": "data.txt"})}},
            ]}, "finish_reason": "tool_calls"}]}
        return {"choices": [{"message": {"role": "assistant", "content": "the value is 42"},
                              "finish_reason": "stop"}]}

    traj_path = tmp_path / "traj.jsonl"
    recorder = TrajectoryRecorder(traj_path, "s1")
    loop = _make_loop(tmp_path, transport, recorder=recorder)
    result = loop.run("what's in data.txt?")
    assert result.tool_call_count == 1
    assert "42" in result.final_message

    events = read_trajectory(traj_path)
    summary = summarize_trajectory(events)
    assert summary["tool_call_count"] == 1
    assert summary["tool_call_breakdown"]["read"] == 1


def test_tool_error_is_reported_back_to_model(tmp_path):
    calls = {"n": 0}

    def transport(url, headers, body):
        calls["n"] += 1
        if calls["n"] == 1:
            # Reference a file that doesn't exist -> tool call fails.
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "read", "arguments": json.dumps({"path": "missing.txt"})}},
            ]}, "finish_reason": "tool_calls"}]}
        # Model sees the tool error message content.
        tool_msg = next(m for m in body["messages"] if m.get("role") == "tool")
        assert "error" in tool_msg["content"]
        return {"choices": [{"message": {"role": "assistant", "content": "I could not read the file"},
                              "finish_reason": "stop"}]}

    loop = _make_loop(tmp_path, transport)
    result = loop.run("read missing.txt")
    assert "could not read" in result.final_message.lower()
    assert result.tool_call_count == 1


def test_max_iterations_exceeded(tmp_path):
    def transport(url, headers, body):
        return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "todo", "arguments": json.dumps({"action": "list"})}},
        ]}, "finish_reason": "tool_calls"}]}

    loop = _make_loop(tmp_path, transport)
    result = loop.run("loop forever", max_iterations=3)
    assert result.stopped_reason == "max_iterations_exceeded"
    assert result.iterations == 3


def test_max_tool_calls_exceeded(tmp_path):
    def transport(url, headers, body):
        return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "todo", "arguments": json.dumps({"action": "list"})}},
        ]}, "finish_reason": "tool_calls"}]}

    loop = _make_loop(tmp_path, transport)
    result = loop.run("loop forever", max_iterations=50, max_tool_calls=2)
    assert result.stopped_reason == "max_tool_calls_exceeded"
    assert result.tool_call_count == 2
