"""Assemble the harness's default built-in tool registry."""
from __future__ import annotations

from pathlib import Path

from openagent.memory.store import MemoryStore
from openagent.skills.registry import SkillRegistry
from openagent.tools.base import ToolRegistry, WorkspaceGuard
from openagent.tools.fs_tools import GlobTool, GrepTool, ReadTool
from openagent.tools.memory_tool import MemoryTool
from openagent.tools.patch_tool import PatchTool
from openagent.tools.shell_tool import ShellTool
from openagent.tools.skill_tool import SkillTool
from openagent.tools.todo_tool import TodoStore, TodoTool


def build_default_tool_registry(
    guard: WorkspaceGuard,
    memory_store: MemoryStore | None = None,
    todo_path: Path | str | None = None,
    shell_timeout_cap: int = 1800,
    skill_registry: SkillRegistry | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadTool(guard))
    registry.register(GlobTool(guard))
    registry.register(GrepTool(guard))
    registry.register(PatchTool(guard))
    registry.register(ShellTool(guard, max_timeout_seconds=shell_timeout_cap))
    registry.register(TodoTool(TodoStore(todo_path or (guard.root / ".openagent_todo.json"))))
    registry.register(MemoryTool(memory_store or MemoryStore(":memory:")))
    registry.register(SkillTool(skill_registry or SkillRegistry()))
    return registry
