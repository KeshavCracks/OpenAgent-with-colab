"""Read / Glob / Grep tools -- the harness's primary read-only file access."""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from openagent.tools.base import Tool, WorkspaceGuard


class ReadTool(Tool):
    name = "read"
    description = "Read a UTF-8 text file from the workspace, optionally a line range."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer", "description": "1-based first line", "default": 1},
            "limit": {"type": "integer", "description": "max lines to return", "default": 2000},
        },
        "required": ["path"],
    }
    permissions = ("fs:read",)

    def __init__(self, guard: WorkspaceGuard):
        self.guard = guard

    def run(self, path: str, offset: int = 1, limit: int = 2000) -> dict:
        resolved = self.guard.resolve(path)
        if not resolved.exists():
            raise FileNotFoundError(f"No such file: {path}")
        if resolved.is_dir():
            raise IsADirectoryError(f"'{path}' is a directory")
        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(offset - 1, 0)
        end = min(start + limit, len(lines))
        snippet = lines[start:end]
        return {
            "path": path,
            "total_lines": len(lines),
            "start_line": start + 1,
            "end_line": end,
            "content": "\n".join(snippet),
        }


class GlobTool(Tool):
    name = "glob"
    description = "Find files under the workspace matching a glob pattern."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "max_results": {"type": "integer", "default": 500},
        },
        "required": ["pattern"],
    }
    permissions = ("fs:read",)

    def __init__(self, guard: WorkspaceGuard):
        self.guard = guard

    def run(self, pattern: str, max_results: int = 500) -> dict:
        root = self.guard.root
        matches = []
        for p in root.rglob("*"):
            if ".git" in p.parts:
                continue
            rel = p.relative_to(root).as_posix()
            if fnmatch.fnmatch(rel, pattern):
                if not self.guard.is_contained(rel):
                    continue
                matches.append(rel)
                if len(matches) >= max_results:
                    break
        return {"pattern": pattern, "matches": sorted(matches)}


class GrepTool(Tool):
    name = "grep"
    description = "Search for a regex pattern across files under the workspace."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "glob": {"type": "string", "default": "**/*"},
            "max_matches": {"type": "integer", "default": 200},
            "case_sensitive": {"type": "boolean", "default": True},
        },
        "required": ["pattern"],
    }
    permissions = ("fs:read",)

    def __init__(self, guard: WorkspaceGuard):
        self.guard = guard

    def run(
        self,
        pattern: str,
        glob: str = "**/*",
        max_matches: int = 200,
        case_sensitive: bool = True,
    ) -> dict:
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)
        root = self.guard.root
        results = []
        for p in root.glob(glob):
            if not p.is_file() or ".git" in p.parts:
                continue
            rel = p.relative_to(root).as_posix()
            if not self.guard.is_contained(rel):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    results.append({"path": rel, "line": lineno, "text": line})
                    if len(results) >= max_matches:
                        return {"pattern": pattern, "matches": results, "truncated": True}
        return {"pattern": pattern, "matches": results, "truncated": False}
