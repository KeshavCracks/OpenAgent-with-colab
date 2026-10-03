from openagent.agent.session import SessionStore
from openagent.agent.subagents import RestrictedToolRegistry, SubagentManager, SubagentSpec
from openagent.agent.trajectory import read_trajectory
from openagent.tools.base import ToolRegistry, WorkspaceGuard
from openagent.tools.fs_tools import GlobTool, ReadTool
from openagent.tools.shell_tool import ShellTool


def _registry(tmp_path):
    guard = WorkspaceGuard(root=tmp_path)
    reg = ToolRegistry()
    reg.register(ReadTool(guard))
    reg.register(GlobTool(guard))
    reg.register(ShellTool(guard))
    return reg


def test_restricted_registry_exposes_only_allowed_tools(tmp_path):
    base = _registry(tmp_path)
    restricted = RestrictedToolRegistry(base, allowed_tools=("read", "glob"))
    assert set(restricted.names()) == {"read", "glob"}
    schema_names = {s["function"]["name"] for s in restricted.schemas()}
    assert schema_names == {"read", "glob"}


def test_restricted_registry_blocks_disallowed_tool(tmp_path):
    base = _registry(tmp_path)
    restricted = RestrictedToolRegistry(base, allowed_tools=("read",))
    try:
        restricted.dispatch("shell", {"command": "echo hi"})
        assert False, "expected PermissionError"
    except PermissionError:
        pass


def test_restricted_registry_allows_dispatch_of_permitted_tool(tmp_path):
    (tmp_path / "f.txt").write_text("hello\n", encoding="utf-8")
    base = _registry(tmp_path)
    restricted = RestrictedToolRegistry(base, allowed_tools=("read",))
    record = restricted.dispatch("read", {"path": "f.txt"})
    assert record.ok


def test_subagent_spawn_success_records_trajectory(tmp_path):
    sessions = SessionStore(tmp_path / "sessions")
    parent = sessions.create(workspace=str(tmp_path))
    manager = SubagentManager(sessions, trajectories_dir=str(tmp_path / "trajectories"))

    spec = SubagentSpec(name="researcher", task="summarize the repo", allowed_tools=("read",),
                         max_tool_calls=5, max_wall_seconds=30)

    def fake_agent_loop(task, tool_registry, recorder, max_tool_calls, max_wall_seconds):
        recorder.record("message", {"role": "assistant", "content": "ok"})
        return {"final_message": "done: " + task, "tool_call_count": 1}

    result = manager.spawn(parent.session_id, spec, _registry(tmp_path), fake_agent_loop)
    assert result.ok
    assert "summarize the repo" in result.summary
    assert result.tool_call_count == 1

    child = sessions.load(result.session_id)
    assert child.parent_session_id == parent.session_id
    assert child.status == "stopped"

    events = read_trajectory(tmp_path / "trajectories" / f"{result.session_id}.jsonl")
    phases = [e.data.get("phase") for e in events if e.type == "phase_switch"]
    assert "subagent_start" in phases
    assert "subagent_end" in phases


def test_subagent_spawn_failure_is_reported_not_raised(tmp_path):
    sessions = SessionStore(tmp_path / "sessions")
    parent = sessions.create(workspace=str(tmp_path))
    manager = SubagentManager(sessions, trajectories_dir=str(tmp_path / "trajectories"))

    spec = SubagentSpec(name="broken", task="do something", allowed_tools=("read",))

    def failing_agent_loop(**kwargs):
        raise RuntimeError("boom")

    result = manager.spawn(parent.session_id, spec, _registry(tmp_path), failing_agent_loop)
    assert result.ok is False
    assert "boom" in result.summary

    child = sessions.load(result.session_id)
    assert child.status == "failed"
