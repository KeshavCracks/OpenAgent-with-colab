import io
import json
from pathlib import Path

from openagent.agent.builtin_tools import build_default_tool_registry
from openagent.mcp.stdio_builtin import serve
from openagent.tools.base import WorkspaceGuard


def _run_requests(tmp_path, requests):
    guard = WorkspaceGuard(root=tmp_path)
    registry = build_default_tool_registry(guard)
    instream = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")
    outstream = io.StringIO()
    serve(registry, instream=instream, outstream=outstream)
    lines = [l for l in outstream.getvalue().splitlines() if l.strip()]
    return [json.loads(l) for l in lines]


def test_initialize_returns_server_info(tmp_path):
    responses = _run_requests(tmp_path, [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}])
    assert responses[0]["result"]["serverInfo"]["name"] == "openagent-builtin"


def test_tools_list_includes_builtin_v1_tools(tmp_path):
    responses = _run_requests(tmp_path, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}])
    names = {t["name"] for t in responses[0]["result"]["tools"]}
    for expected in ("read", "glob", "grep", "patch", "shell", "todo", "memory", "skills"):
        assert expected in names


def test_tools_call_read_succeeds(tmp_path):
    (tmp_path / "hello.txt").write_text("hi there\n", encoding="utf-8")
    responses = _run_requests(tmp_path, [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "read", "arguments": {"path": "hello.txt"}}},
    ])
    assert "result" in responses[0]
    assert "error" not in responses[0]


def test_tools_call_unknown_tool_returns_error(tmp_path):
    responses = _run_requests(tmp_path, [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "nonexistent_tool", "arguments": {}}},
    ])
    assert "error" in responses[0]
    assert responses[0]["error"]["code"] == -32000


def test_tools_call_workspace_escape_is_reported_as_tool_error_not_crash(tmp_path):
    responses = _run_requests(tmp_path, [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "read", "arguments": {"path": "/etc/passwd"}}},
    ])
    assert "error" in responses[0]


def test_unknown_method_returns_method_not_found(tmp_path):
    responses = _run_requests(tmp_path, [{"jsonrpc": "2.0", "id": 1, "method": "bogus/method", "params": {}}])
    assert responses[0]["error"]["code"] == -32601


def test_malformed_json_lines_are_skipped_not_fatal(tmp_path):
    guard = WorkspaceGuard(root=tmp_path)
    registry = build_default_tool_registry(guard)
    instream = io.StringIO("not json at all\n" + json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n")
    outstream = io.StringIO()
    serve(registry, instream=instream, outstream=outstream)
    lines = [l for l in outstream.getvalue().splitlines() if l.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["result"]["serverInfo"]["name"] == "openagent-builtin"


def test_blank_lines_are_ignored(tmp_path):
    guard = WorkspaceGuard(root=tmp_path)
    registry = build_default_tool_registry(guard)
    instream = io.StringIO("\n\n" + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n\n")
    outstream = io.StringIO()
    serve(registry, instream=instream, outstream=outstream)
    lines = [l for l in outstream.getvalue().splitlines() if l.strip()]
    assert len(lines) == 1
