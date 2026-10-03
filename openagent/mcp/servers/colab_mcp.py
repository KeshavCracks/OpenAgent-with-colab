"""Adapter: github.com/googlecolab/colab-mcp as this harness's ColabExecClient.

colab-mcp bridges to a Colab notebook already open in the user's browser; it
is launched as `uvx git+https://github.com/googlecolab/colab-mcp` by an MCP
client that supports `notifications/tools/list_changed`. This adapter wraps
that stdio server behind the small `execute(code) -> ColabExecResult`
interface that `openagent.providers.colab.ColabDriver` expects, so the rest
of the harness never has to know about MCP framing.

This module intentionally does not hardcode a tool name for "execute a code
cell", because colab-mcp's exact tool surface may evolve; instead it
discovers it once via `tools/list` and caches the match. If none is found,
callers get a clear MCPError rather than a silent no-op.
"""
from __future__ import annotations

import dataclasses

from openagent.mcp.manager import MCPServerSpec, StdioMCPClient, MCPError
from openagent.providers.colab import ColabExecResult


def default_colab_mcp_spec(extra_env: dict | None = None) -> MCPServerSpec:
    return MCPServerSpec(
        name="colab-mcp",
        command=["uvx", "git+https://github.com/googlecolab/colab-mcp"],
        env=extra_env,
        allowed_permissions=("colab:execute_cell", "colab:read_output"),
        public_endpoint=False,
    )


_EXEC_TOOL_CANDIDATES = ("execute_cell", "run_cell", "execute_code", "run_code")


class ColabMcpExecClient:
    """Implements the `ColabExecClient` callable protocol via colab-mcp."""

    def __init__(self, spec: MCPServerSpec | None = None, client: StdioMCPClient | None = None):
        self.spec = spec or default_colab_mcp_spec()
        self.client = client or StdioMCPClient(self.spec)
        self._started = False
        self._exec_tool_name: str | None = None

    def _ensure_started(self) -> None:
        if not self._started:
            self.client.start()
            self._started = True
            tools = {t["name"] for t in self.client.list_tools()}
            for candidate in _EXEC_TOOL_CANDIDATES:
                if candidate in tools:
                    self._exec_tool_name = candidate
                    break
            if self._exec_tool_name is None:
                raise MCPError(
                    "colab-mcp did not expose a recognized code-execution tool "
                    f"(looked for {_EXEC_TOOL_CANDIDATES}); check the installed version."
                )

    def __call__(self, code: str) -> ColabExecResult:
        self._ensure_started()
        try:
            result = self.client.call_tool(self._exec_tool_name, {"code": code}, timeout=120)
            return ColabExecResult(
                ok=True,
                stdout=str(result.get("stdout", result.get("output", ""))),
                stderr=str(result.get("stderr", "")),
            )
        except MCPError as exc:
            return ColabExecResult(ok=False, stderr=str(exc))

    def close(self) -> None:
        if self._started:
            self.client.stop()
            self._started = False
