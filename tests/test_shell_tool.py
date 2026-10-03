from pathlib import Path

import pytest

from openagent.tools.base import WorkspaceGuard
from openagent.tools.shell_tool import ShellTool


def test_shell_runs_command(tmp_path):
    guard = WorkspaceGuard(root=tmp_path)
    tool = ShellTool(guard)
    result = tool.run(command="echo hello")
    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]
    assert result["timed_out"] is False


def test_shell_enforces_timeout(tmp_path):
    guard = WorkspaceGuard(root=tmp_path)
    tool = ShellTool(guard)
    result = tool.run(command="sleep 5", timeout_seconds=1)
    assert result["timed_out"] is True
    assert result["duration_seconds"] < 4


def test_shell_cwd_confined_to_workspace(tmp_path):
    guard = WorkspaceGuard(root=tmp_path)
    tool = ShellTool(guard)
    with pytest.raises(Exception):
        tool.run(command="pwd", cwd="/etc")


def test_shell_timeout_capped_by_max(tmp_path):
    guard = WorkspaceGuard(root=tmp_path)
    tool = ShellTool(guard, max_timeout_seconds=2)
    result = tool.run(command="sleep 5", timeout_seconds=100)
    assert result["timed_out"] is True
    assert result["duration_seconds"] < 4
