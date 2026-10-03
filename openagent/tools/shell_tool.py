"""Time-limited shell execution, confined to the workspace root."""
from __future__ import annotations

import os
import signal
import subprocess
import time

from openagent.tools.base import Tool, WorkspaceGuard


class ShellTimeoutError(TimeoutError):
    pass


class ShellTool(Tool):
    name = "shell"
    description = (
        "Run a shell command with a hard timeout, cwd confined to the workspace. "
        "Use for tests, builds, linters, and other short-lived commands."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "cwd": {"type": "string", "default": "."},
            "timeout_seconds": {"type": "integer", "default": 30, "maximum": 1800},
        },
        "required": ["command"],
    }
    permissions = ("shell:exec",)

    def __init__(self, guard: WorkspaceGuard, max_timeout_seconds: int = 1800):
        self.guard = guard
        self.max_timeout_seconds = max_timeout_seconds

    def run(self, command: str, cwd: str = ".", timeout_seconds: int = 30) -> dict:
        timeout_seconds = min(timeout_seconds, self.max_timeout_seconds)
        resolved_cwd = self.guard.resolve(cwd)
        if not resolved_cwd.is_dir():
            raise NotADirectoryError(f"cwd '{cwd}' is not a directory in the workspace")

        started = time.time()
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(resolved_cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,  # own process group -> can kill children too
        )
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                stdout, stderr = proc.communicate(timeout=5)
            except Exception:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                stdout, stderr = proc.communicate()
        duration = time.time() - started
        return {
            "command": command,
            "cwd": cwd,
            "exit_code": proc.returncode,
            "timed_out": timed_out,
            "duration_seconds": round(duration, 3),
            "stdout": stdout[-200_000:] if stdout else "",
            "stderr": stderr[-200_000:] if stderr else "",
        }
