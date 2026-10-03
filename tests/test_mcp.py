import sys
from pathlib import Path

import pytest

from openagent.agent.builtin_tools import build_default_tool_registry
from openagent.mcp.manager import (
    MCPError,
    MCPManager,
    MCPServerSpec,
    MCPTimeoutError,
    StdioMCPClient,
)
from openagent.tools.base import WorkspaceGuard

FIXTURE = str(Path(__file__).parent / "fixtures" / "fake_mcp_server.py")


def _spec() -> MCPServerSpec:
    return MCPServerSpec(name="fake-mcp", command=[sys.executable, FIXTURE])


def test_public_endpoint_refused():
    spec = MCPServerSpec(name="bad", command=["true"], public_endpoint=True)
    manager = MCPManager(build_default_tool_registry(WorkspaceGuard(root=Path.cwd())), WorkspaceGuard(root=Path.cwd()))
    with pytest.raises(MCPError):
        manager.register_external(spec)


def test_stdio_client_startup_and_tool_list():
    client = StdioMCPClient(_spec())
    client.start()
    try:
        assert client.is_alive()
        tools = client.list_tools()
        assert any(t["name"] == "echo" for t in tools)
    finally:
        client.stop()
    assert not client.is_alive()


def test_stdio_client_call_tool():
    client = StdioMCPClient(_spec())
    client.start()
    try:
        result = client.call_tool("echo", {"hello": "world"})
        assert result["output"] == {"hello": "world"}
    finally:
        client.stop()


def test_stdio_client_timeout_on_slow_tool():
    client = StdioMCPClient(_spec())
    client.start()
    try:
        with pytest.raises(MCPTimeoutError):
            client.call_tool("slow_tool", {}, timeout=0.5)
    finally:
        client.stop()


def test_stdio_client_unknown_tool_fails_fast():
    client = StdioMCPClient(_spec())
    client.start()
    try:
        with pytest.raises(MCPError):
            client.call_tool("does_not_exist", {}, timeout=5)
    finally:
        client.stop()


def test_validate_server_full_lifecycle():
    guard = WorkspaceGuard(root=Path.cwd())
    manager = MCPManager(build_default_tool_registry(guard), guard)
    result = manager.validate_server(_spec())
    assert result.startup_ok
    assert result.tool_list_ok
    assert result.timeout_ok
    assert result.permission_ok
    assert result.workspace_containment_ok
    assert result.failure_handling_ok
    assert result.all_passed


def test_validate_server_startup_failure_reported():
    guard = WorkspaceGuard(root=Path.cwd())
    manager = MCPManager(build_default_tool_registry(guard), guard)
    bad_spec = MCPServerSpec(name="nonexistent-binary", command=["this-binary-does-not-exist-xyz"])
    result = manager.validate_server(bad_spec)
    assert not result.startup_ok
    assert not result.all_passed


def test_builtin_tools_exposed_as_mcp_shaped_list():
    guard = WorkspaceGuard(root=Path.cwd())
    manager = MCPManager(build_default_tool_registry(guard), guard)
    tools = manager.builtin_tool_list()
    names = {t["function"]["name"] for t in tools}
    assert {"read", "glob", "grep", "patch", "shell", "todo", "memory", "skills"}.issubset(names)
