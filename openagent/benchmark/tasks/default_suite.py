"""Default offline-runnable benchmark suite: smoke, tool-use, multi-file
coding, research, and browser-approval acceptance checks."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from openagent.benchmark.harness import BenchmarkHarness, BenchmarkResult, BenchmarkTask
from openagent.browser.browser_use import ActionKind, ApprovalRequiredError, BrowserAction, BrowserSession
from openagent.research.agent_reach import AgentReach, Citation
from openagent.tools.base import ToolRegistry, WorkspaceGuard
from openagent.tools.fs_tools import GlobTool, GrepTool, ReadTool
from openagent.tools.patch_tool import PatchTool


def _smoke_task() -> BenchmarkResult:
    started = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        guard = WorkspaceGuard(root=Path(tmp))
        (Path(tmp) / "hello.txt").write_text("hello world\n", encoding="utf-8")
        registry = ToolRegistry()
        registry.register(ReadTool(guard))
        record = registry.dispatch("read", {"path": "hello.txt"})
        ok = record.ok and "hello world" in record.result["content"]
        return BenchmarkResult("smoke_read_tool", "smoke", ok, time.time() - started,
                                detail="read tool round-trip")


def _tool_use_multi_step_task() -> BenchmarkResult:
    started = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        guard = WorkspaceGuard(root=Path(tmp))
        (Path(tmp) / "a.txt").write_text("alpha\nbeta\n", encoding="utf-8")
        (Path(tmp) / "b.txt").write_text("gamma\n", encoding="utf-8")
        registry = ToolRegistry()
        registry.register(GlobTool(guard))
        registry.register(GrepTool(guard))
        glob_record = registry.dispatch("glob", {"pattern": "*.txt"})
        grep_record = registry.dispatch("grep", {"pattern": "beta"})
        ok = (
            glob_record.ok and set(glob_record.result["matches"]) == {"a.txt", "b.txt"}
            and grep_record.ok and len(grep_record.result["matches"]) == 1
        )
        return BenchmarkResult("tool_use_glob_then_grep", "tool_use", ok, time.time() - started)


def _multi_file_coding_task() -> BenchmarkResult:
    started = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        guard = WorkspaceGuard(root=Path(tmp))
        (Path(tmp) / "mod_a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
        (Path(tmp) / "mod_b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
        diff = (
            "--- a/mod_a.py\n+++ b/mod_a.py\n@@ -1,2 +1,2 @@\n def a():\n-    return 1\n+    return 100\n"
            "--- a/mod_b.py\n+++ b/mod_b.py\n@@ -1,2 +1,2 @@\n def b():\n-    return 2\n+    return 200\n"
        )
        registry = ToolRegistry()
        registry.register(PatchTool(guard))
        record = registry.dispatch("patch", {"diff": diff})
        ok = (
            record.ok
            and "return 100" in (Path(tmp) / "mod_a.py").read_text()
            and "return 200" in (Path(tmp) / "mod_b.py").read_text()
        )
        return BenchmarkResult("multi_file_patch", "multi_file_coding", ok, time.time() - started)


def _research_citation_task() -> BenchmarkResult:
    started = time.time()
    reach = AgentReach()
    reach.register_channel("fake_docs", lambda q: [Citation(url="https://example.org/doc", title="Doc", snippet=q)])
    result = reach.query("fake_docs", "how do I configure the harness?")
    ok = len(result.citations) == 1 and result.citations[0].url.startswith("https://")
    return BenchmarkResult("research_channel_returns_citation", "research", ok, time.time() - started)


def _browser_approval_gate_task() -> BenchmarkResult:
    started = time.time()
    session = BrowserSession(backend=lambda action: {"ok": True})
    blocked = False
    try:
        session.perform(BrowserAction(kind=ActionKind.LOGIN, target="https://example.com/login"))
    except ApprovalRequiredError:
        blocked = True
    approved_ok = False
    try:
        session.perform(BrowserAction(kind=ActionKind.LOGIN, target="https://example.com/login",
                                       approval_token="user-approved-123"))
        approved_ok = True
    except ApprovalRequiredError:
        approved_ok = False
    ok = blocked and approved_ok
    return BenchmarkResult("browser_requires_approval_for_login", "browser", ok, time.time() - started)


def build_default_suite() -> BenchmarkHarness:
    harness = BenchmarkHarness()
    harness.register(BenchmarkTask("smoke_read_tool", "smoke", _smoke_task))
    harness.register(BenchmarkTask("tool_use_glob_then_grep", "tool_use", _tool_use_multi_step_task))
    harness.register(BenchmarkTask("multi_file_patch", "multi_file_coding", _multi_file_coding_task))
    harness.register(BenchmarkTask("research_channel_returns_citation", "research", _research_citation_task))
    harness.register(BenchmarkTask("browser_requires_approval_for_login", "browser", _browser_approval_gate_task))
    return harness
