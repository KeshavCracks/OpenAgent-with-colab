from pathlib import Path

import pytest

from openagent.tools.base import WorkspaceGuard, WorkspaceViolationError
from openagent.tools.fs_tools import GlobTool, GrepTool, ReadTool


def _setup_workspace(tmp_path: Path) -> WorkspaceGuard:
    (tmp_path / "a.txt").write_text("hello\nworld\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("def f():\n    return 42\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    return WorkspaceGuard(root=tmp_path, deny_paths=(".env",))


def test_read_tool_reads_content(tmp_path):
    guard = _setup_workspace(tmp_path)
    tool = ReadTool(guard)
    result = tool.run(path="a.txt")
    assert "hello" in result["content"]
    assert result["total_lines"] == 2


def test_read_tool_offset_limit(tmp_path):
    guard = _setup_workspace(tmp_path)
    tool = ReadTool(guard)
    result = tool.run(path="a.txt", offset=2, limit=1)
    assert result["content"] == "world"


def test_read_tool_missing_file_raises(tmp_path):
    guard = _setup_workspace(tmp_path)
    tool = ReadTool(guard)
    with pytest.raises(FileNotFoundError):
        tool.run(path="missing.txt")


def test_workspace_guard_blocks_escape(tmp_path):
    guard = _setup_workspace(tmp_path)
    with pytest.raises(WorkspaceViolationError):
        guard.resolve("../outside.txt")
    with pytest.raises(WorkspaceViolationError):
        guard.resolve("/etc/passwd")


def test_workspace_guard_blocks_denylist(tmp_path):
    guard = _setup_workspace(tmp_path)
    with pytest.raises(WorkspaceViolationError):
        guard.resolve(".env")


def test_glob_tool_finds_files(tmp_path):
    guard = _setup_workspace(tmp_path)
    tool = GlobTool(guard)
    result = tool.run(pattern="**/*.py")
    assert result["matches"] == ["sub/b.py"]


def test_glob_tool_excludes_denied_paths(tmp_path):
    guard = _setup_workspace(tmp_path)
    tool = GlobTool(guard)
    result = tool.run(pattern="*")
    assert ".env" not in result["matches"]


def test_grep_tool_finds_pattern(tmp_path):
    guard = _setup_workspace(tmp_path)
    tool = GrepTool(guard)
    result = tool.run(pattern="return 42")
    assert len(result["matches"]) == 1
    assert result["matches"][0]["path"] == "sub/b.py"


def test_grep_tool_case_insensitive(tmp_path):
    guard = _setup_workspace(tmp_path)
    tool = GrepTool(guard)
    result = tool.run(pattern="HELLO", case_sensitive=False)
    assert len(result["matches"]) == 1
