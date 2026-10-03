"""Unified-diff patch tool: apply patches to the workspace without corruption.

Safety properties:
  * Context lines in every hunk are verified against the current file content
    before anything is written -- a mismatch aborts the whole patch (atomic,
    all-or-nothing across every hunk in the diff).
  * Writes go to a temp file in the same directory and are renamed into place,
    so a crash mid-write can never leave a half-written file.
  * New-file and delete-file hunks (`--- /dev/null` / `+++ /dev/null`) are
    supported explicitly rather than inferred.
"""
from __future__ import annotations

import dataclasses
import os
import re
import tempfile
from pathlib import Path

from openagent.tools.base import Tool, WorkspaceGuard

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(ValueError):
    pass


@dataclasses.dataclass
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    lines: list[str]  # with leading ' ', '+', '-' markers preserved


@dataclasses.dataclass
class FilePatch:
    old_path: str | None
    new_path: str | None
    hunks: list[Hunk]

    @property
    def is_new_file(self) -> bool:
        return self.old_path in (None, "/dev/null")

    @property
    def is_delete(self) -> bool:
        return self.new_path in (None, "/dev/null")


def parse_unified_diff(text: str) -> list[FilePatch]:
    lines = text.splitlines()
    patches: list[FilePatch] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            old_path = line[4:].strip()
            old_path = re.sub(r"^a/", "", old_path)
            if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
                raise PatchError(f"Malformed diff: '---' not followed by '+++' at line {i + 1}")
            new_path = lines[i + 1][4:].strip()
            new_path = re.sub(r"^b/", "", new_path)
            i += 2
            hunks: list[Hunk] = []
            while i < len(lines) and lines[i].startswith("@@"):
                m = _HUNK_HEADER.match(lines[i])
                if not m:
                    raise PatchError(f"Malformed hunk header: {lines[i]!r}")
                old_start, old_len, new_start, new_len = m.groups()
                old_len = int(old_len) if old_len else 1
                new_len = int(new_len) if new_len else 1
                i += 1
                body: list[str] = []
                consumed_old = 0
                consumed_new = 0
                while i < len(lines) and not (consumed_old >= old_len and consumed_new >= new_len):
                    hl = lines[i]
                    if hl.startswith(("---", "+++", "@@")):
                        break
                    if hl.startswith("+"):
                        consumed_new += 1
                    elif hl.startswith("-"):
                        consumed_old += 1
                    elif hl.startswith(" ") or hl == "":
                        consumed_old += 1
                        consumed_new += 1
                    else:
                        # Tolerate diffs without a leading space on context lines.
                        hl = " " + hl
                        consumed_old += 1
                        consumed_new += 1
                    body.append(hl)
                    i += 1
                hunks.append(Hunk(int(old_start), old_len, int(new_start), new_len, body))
            patches.append(FilePatch(old_path=old_path, new_path=new_path, hunks=hunks))
        else:
            i += 1
    if not patches:
        raise PatchError("No valid '--- file' / '+++ file' diff headers found")
    return patches


def _apply_hunks_to_lines(original_lines: list[str], hunks: list[Hunk], label: str) -> list[str]:
    result: list[str] = []
    cursor = 0  # 0-based index into original_lines
    for hunk in hunks:
        start = max(hunk.old_start - 1, 0)
        if start < cursor:
            raise PatchError(f"{label}: overlapping/out-of-order hunks")
        result.extend(original_lines[cursor:start])
        pos = start
        for hl in hunk.lines:
            tag, content = hl[0], hl[1:]
            if tag == " ":
                if pos >= len(original_lines) or original_lines[pos] != content:
                    raise PatchError(
                        f"{label}: context mismatch at line {pos + 1} "
                        f"(expected {content!r}, found {original_lines[pos] if pos < len(original_lines) else '<eof>'!r})"
                    )
                result.append(content)
                pos += 1
            elif tag == "-":
                if pos >= len(original_lines) or original_lines[pos] != content:
                    raise PatchError(
                        f"{label}: deletion mismatch at line {pos + 1} "
                        f"(expected {content!r}, found {original_lines[pos] if pos < len(original_lines) else '<eof>'!r})"
                    )
                pos += 1
            elif tag == "+":
                result.append(content)
        cursor = pos
    result.extend(original_lines[cursor:])
    return result


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def apply_patch(guard: WorkspaceGuard, diff_text: str, dry_run: bool = False) -> dict:
    file_patches = parse_unified_diff(diff_text)
    plan: list[dict] = []

    for fp in file_patches:
        target_rel = fp.new_path if not fp.is_delete else fp.old_path
        if target_rel is None:
            raise PatchError("Patch has neither a usable old nor new path")
        target = guard.resolve(target_rel)

        if fp.is_new_file:
            original_lines: list[str] = []
        else:
            old_target = guard.resolve(fp.old_path)
            if not old_target.exists():
                raise PatchError(f"Cannot patch '{fp.old_path}': file does not exist")
            original_lines = old_target.read_text(encoding="utf-8").splitlines()

        if fp.is_delete:
            plan.append({"action": "delete", "path": fp.old_path})
            continue

        new_lines = _apply_hunks_to_lines(original_lines, fp.hunks, label=target_rel)
        new_content = "\n".join(new_lines)
        if new_lines:
            new_content += "\n"
        plan.append({"action": "write", "path": target_rel, "content": new_content, "resolved": target})

    if dry_run:
        return {"applied": False, "dry_run": True, "files": [p["path"] for p in plan]}

    # All validation passed for every file -- now perform the writes.
    for item in plan:
        if item["action"] == "delete":
            resolved = guard.resolve(item["path"])
            if resolved.exists():
                resolved.unlink()
        else:
            _atomic_write(item["resolved"], item["content"])

    return {"applied": True, "dry_run": False, "files": [p["path"] for p in plan]}


class PatchTool(Tool):
    name = "patch"
    description = (
        "Apply a unified diff to one or more files in the workspace. All hunks "
        "are validated against current file contents before anything is "
        "written (atomic, all-or-nothing)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "diff": {"type": "string", "description": "unified diff text"},
            "dry_run": {"type": "boolean", "default": False},
        },
        "required": ["diff"],
    }
    permissions = ("fs:read", "fs:write")

    def __init__(self, guard: WorkspaceGuard):
        self.guard = guard

    def run(self, diff: str, dry_run: bool = False) -> dict:
        return apply_patch(self.guard, diff, dry_run=dry_run)
