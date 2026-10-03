"""Dependency auditing wrapper. Shells out to an installed auditor
(`pip-audit` for Python, `npm audit --json` for Node) when available;
reports "not available" rather than silently skipping when it isn't,
so a missing tool is visible in the quality-gate output."""
from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
from pathlib import Path


@dataclasses.dataclass
class DependencyAuditResult:
    ecosystem: str
    tool_available: bool
    vulnerabilities: list[dict]
    raw_output: str = ""
    error: str | None = None


def _run(cmd: list[str], cwd: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def run_dependency_audit(workspace: Path | str, ecosystem: str = "python") -> DependencyAuditResult:
    workspace = str(workspace)
    if ecosystem == "python":
        if shutil.which("pip-audit") is None:
            return DependencyAuditResult("python", tool_available=False, vulnerabilities=[],
                                          error="pip-audit is not installed")
        try:
            proc = _run(["pip-audit", "-f", "json"], cwd=workspace)
            data = json.loads(proc.stdout or "[]")
            vulns = data if isinstance(data, list) else data.get("dependencies", [])
            return DependencyAuditResult("python", True, vulns, raw_output=proc.stdout)
        except Exception as exc:  # noqa: BLE001
            return DependencyAuditResult("python", True, [], error=str(exc))
    if ecosystem == "node":
        if shutil.which("npm") is None:
            return DependencyAuditResult("node", tool_available=False, vulnerabilities=[],
                                          error="npm is not installed")
        try:
            proc = _run(["npm", "audit", "--json"], cwd=workspace)
            data = json.loads(proc.stdout or "{}")
            vulns = list((data.get("vulnerabilities") or {}).values())
            return DependencyAuditResult("node", True, vulns, raw_output=proc.stdout)
        except Exception as exc:  # noqa: BLE001
            return DependencyAuditResult("node", True, [], error=str(exc))
    raise ValueError(f"Unsupported ecosystem: {ecosystem}")
