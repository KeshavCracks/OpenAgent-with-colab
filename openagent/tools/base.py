"""Tool base classes and the workspace containment guard shared by all tools.

Every built-in tool (read, glob/grep, patch, shell, todo, memory, skills) and
every MCP-exposed tool is routed through :class:`WorkspaceGuard` so that file
and shell access cannot escape the configured workspace root, regardless of
whether the request came from the model, a skill, or an MCP server.
"""
from __future__ import annotations

import dataclasses
import os
import time
from pathlib import Path
from typing import Any, Callable


class WorkspaceViolationError(PermissionError):
    pass


@dataclasses.dataclass
class WorkspaceGuard:
    root: Path
    deny_paths: tuple[str, ...] = (".git/config", ".git/credentials", ".env", ".netrc")

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()

    def resolve(self, relative_or_absolute: str) -> Path:
        candidate = Path(relative_or_absolute)
        path = candidate if candidate.is_absolute() else self.root / candidate
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceViolationError(
                f"Path '{relative_or_absolute}' escapes workspace root '{self.root}'"
            ) from exc
        rel = resolved.relative_to(self.root).as_posix()
        for deny in self.deny_paths:
            if rel == deny or rel.startswith(deny.rstrip("/") + "/"):
                raise WorkspaceViolationError(f"Path '{rel}' is in the deny-list")
        return resolved

    def is_contained(self, path: str) -> bool:
        try:
            self.resolve(path)
            return True
        except WorkspaceViolationError:
            return False


@dataclasses.dataclass
class ToolCallRecord:
    tool: str
    arguments: dict[str, Any]
    result: Any
    ok: bool
    started_at: float
    finished_at: float
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        return (self.finished_at - self.started_at) * 1000.0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class Tool:
    """Base class for a harness tool.

    Subclasses set `name`, `description`, `parameters` (JSON schema dict) and
    implement `run`. `permissions` documents what the tool is allowed to
    touch, surfaced in tool-call-detail views and MCP validation tests.
    """

    name: str = "tool"
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}
    permissions: tuple[str, ...] = ()

    def run(self, **kwargs: Any) -> Any:  # pragma: no cover - abstract
        raise NotImplementedError

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def __call__(self, **kwargs: Any) -> ToolCallRecord:
        started = time.time()
        try:
            result = self.run(**kwargs)
            return ToolCallRecord(
                tool=self.name, arguments=kwargs, result=result, ok=True,
                started_at=started, finished_at=time.time(),
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to caller as a record
            return ToolCallRecord(
                tool=self.name, arguments=kwargs, result=None, ok=False,
                started_at=started, finished_at=time.time(), error=str(exc),
            )


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[dict]:
        return [t.to_openai_schema() for t in self._tools.values()]

    def dispatch(self, name: str, arguments: dict) -> ToolCallRecord:
        return self.get(name)(**arguments)
