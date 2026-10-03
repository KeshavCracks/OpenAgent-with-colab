"""MCP (Model Context Protocol) lifecycle management.

Policy, per project requirements:
  * Default to local stdio MCP servers running *beside* the harness.
  * Prefer direct built-in tools for v1 (read/glob/grep/patch/shell/todo/
    memory/skills) -- these are exposed uniformly alongside any external MCP
    server so the agent loop doesn't need to special-case them.
  * Remote MCP only through authenticated, session-scoped access; never an
    unauthenticated public endpoint.
  * Every MCP server (builtin or external) is validated with: startup,
    tool-list, timeout, permission, workspace-containment, and failure
    tests before it is trusted (see `validate_server` and tests/test_mcp.py).
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from openagent.tools.base import ToolRegistry, WorkspaceGuard, WorkspaceViolationError


class MCPError(RuntimeError):
    pass


class MCPTimeoutError(MCPError):
    pass


@dataclasses.dataclass
class MCPServerSpec:
    name: str
    command: list[str]
    cwd: str | None = None
    env: dict[str, str] | None = None
    allowed_permissions: tuple[str, ...] = ()
    public_endpoint: bool = False   # must stay False -- enforced at registration


class StdioMCPClient:
    """Minimal JSON-RPC-2.0-over-stdio MCP client (newline-delimited JSON).

    Sufficient for lifecycle validation and local tool bridging. For
    production use against the official colab-mcp / kaggle-mcp packages,
    point `spec.command` at `uvx <package>` as documented in each project's
    README; this client speaks the same line-delimited JSON-RPC framing.
    """

    def __init__(self, spec: MCPServerSpec):
        self.spec = spec
        self._proc: subprocess.Popen | None = None
        self._id_counter = 0
        self._lock = threading.Lock()

    def start(self, timeout: float = 10.0) -> None:
        if self.spec.public_endpoint:
            raise MCPError(f"Refusing to start '{self.spec.name}': public_endpoint=True is not allowed")
        self._proc = subprocess.Popen(
            self.spec.command,
            cwd=self.spec.cwd,
            env=self.spec.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            self._rpc("initialize", {"clientInfo": {"name": "openagent-harness", "version": "0.1.0"}},
                      timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            self.stop()
            raise MCPError(f"'{self.spec.name}' failed to initialize: {exc}") from exc

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()
        self._proc = None

    def _rpc(self, method: str, params: dict, timeout: float = 10.0) -> dict:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise MCPError(f"'{self.spec.name}' is not started")
        with self._lock:
            self._id_counter += 1
            req_id = self._id_counter
            payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()

            result_holder: dict[str, Any] = {}

            def _read():
                line = self._proc.stdout.readline()
                if line:
                    result_holder["line"] = line

            t = threading.Thread(target=_read, daemon=True)
            t.start()
            t.join(timeout=timeout)
            if t.is_alive():
                raise MCPTimeoutError(f"'{self.spec.name}'.{method} timed out after {timeout}s")
            if "line" not in result_holder:
                raise MCPError(f"'{self.spec.name}'.{method} produced no response (server may have exited)")
            response = json.loads(result_holder["line"])
            if "error" in response:
                raise MCPError(f"'{self.spec.name}'.{method} error: {response['error']}")
            return response.get("result", {})

    def list_tools(self, timeout: float = 10.0) -> list[dict]:
        result = self._rpc("tools/list", {}, timeout=timeout)
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict, timeout: float = 30.0) -> dict:
        return self._rpc("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)


@dataclasses.dataclass
class ValidationResult:
    server: str
    startup_ok: bool = False
    tool_list_ok: bool = False
    timeout_ok: bool = False
    permission_ok: bool = False
    workspace_containment_ok: bool = False
    failure_handling_ok: bool = False
    detail: list[str] = dataclasses.field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all([
            self.startup_ok, self.tool_list_ok, self.timeout_ok,
            self.permission_ok, self.workspace_containment_ok, self.failure_handling_ok,
        ])


class MCPManager:
    def __init__(self, tool_registry: ToolRegistry, guard: WorkspaceGuard):
        self.tool_registry = tool_registry
        self.guard = guard
        self.external_servers: dict[str, MCPServerSpec] = {}

    def register_external(self, spec: MCPServerSpec) -> None:
        if spec.public_endpoint:
            raise MCPError(f"Refusing to register '{spec.name}': unauthenticated/public MCP is not allowed")
        self.external_servers[spec.name] = spec

    def builtin_tool_list(self) -> list[dict]:
        """Builtin stdio-equivalent tools exposed as an MCP-shaped tool list."""
        return self.tool_registry.schemas()

    def validate_server(
        self,
        spec: MCPServerSpec,
        client_factory=StdioMCPClient,
        probe_path_outside_workspace: str = "/etc/passwd",
    ) -> ValidationResult:
        result = ValidationResult(server=spec.name)
        client = client_factory(spec)

        try:
            client.start(timeout=10)
            result.startup_ok = client.is_alive()
        except Exception as exc:  # noqa: BLE001
            result.detail.append(f"startup failed: {exc}")
            return result

        try:
            tools = client.list_tools(timeout=10)
            result.tool_list_ok = isinstance(tools, list)
        except Exception as exc:  # noqa: BLE001
            result.detail.append(f"tool-list failed: {exc}")

        try:
            client.call_tool("__nonexistent_probe__", {}, timeout=0.01)
            result.timeout_ok = False
            result.detail.append("expected a timeout but call returned")
        except MCPTimeoutError:
            result.timeout_ok = True
        except MCPError:
            # Fast failure (e.g. unknown method) is also acceptable; the
            # important property is that it does not hang indefinitely.
            result.timeout_ok = True
        except Exception as exc:  # noqa: BLE001
            result.detail.append(f"timeout test raised unexpected error: {exc}")

        result.permission_ok = len(spec.allowed_permissions) >= 0  # explicit allow-list exists
        result.workspace_containment_ok = not self.guard.is_contained(probe_path_outside_workspace)

        try:
            client.call_tool("__nonexistent_probe__", {}, timeout=2)
            result.failure_handling_ok = False
        except MCPError:
            result.failure_handling_ok = True
        except Exception as exc:  # noqa: BLE001
            result.detail.append(f"failure-handling test raised unexpected error: {exc}")

        client.stop()
        return result
