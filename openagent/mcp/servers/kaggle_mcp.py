"""Adapter: github.com/Galaxy-Dawn/kaggle-mcp as this harness's KaggleExecClient.

kaggle-mcp is a local stdio MCP server wrapping the Kaggle REST API
(competitions, datasets, kernels, models, benchmarks, discussions) --
installed via `uvx kaggle-mcp-server` and authenticated with
KAGGLE_API_TOKEN or ~/.kaggle/kaggle.json. Unlike colab-mcp it has no live
code-exec channel into a running kernel; this adapter maps the batch-style
push/status/output kernel tools onto `openagent.providers.kaggle.KaggleExecClient`.
"""
from __future__ import annotations

from pathlib import Path

from openagent.mcp.manager import MCPServerSpec, StdioMCPClient, MCPError
from openagent.providers.kaggle import (
    KaggleExecClient,
    KaggleKernelHandle,
    KaggleOutputResult,
    KaggleStatusResult,
)


def default_kaggle_mcp_spec(api_token_env: str = "KAGGLE_API_TOKEN") -> MCPServerSpec:
    return MCPServerSpec(
        name="kaggle-mcp",
        command=["uvx", "kaggle-mcp-server"],
        env=None,  # the real token is read from the environment by the subprocess,
                    # never passed as a literal in code/config (see docs/security.md)
        allowed_permissions=("kaggle:push_kernel", "kaggle:read_status", "kaggle:read_output"),
        public_endpoint=False,
    )


class KaggleMcpExecClient(KaggleExecClient):
    def __init__(self, spec: MCPServerSpec | None = None, client: StdioMCPClient | None = None):
        self.spec = spec or default_kaggle_mcp_spec()
        self.client = client or StdioMCPClient(self.spec)
        self._started = False

    def _ensure_started(self) -> None:
        if not self._started:
            self.client.start()
            self._started = True

    def push_kernel(self, kernel_dir: str) -> KaggleKernelHandle:
        self._ensure_started()
        result = self.client.call_tool("push_kernel", {"folder": kernel_dir}, timeout=60)
        ref = result.get("kernel_ref") or result.get("id")
        if not ref:
            raise MCPError(f"kaggle-mcp push_kernel returned no kernel ref: {result}")
        return KaggleKernelHandle(kernel_ref=ref)

    def get_status(self, handle: KaggleKernelHandle) -> KaggleStatusResult:
        self._ensure_started()
        result = self.client.call_tool("kernel_status", {"kernel_ref": handle.kernel_ref}, timeout=30)
        return KaggleStatusResult(status=result.get("status", "unknown"), detail=str(result))

    def get_output(self, handle: KaggleKernelHandle) -> KaggleOutputResult:
        self._ensure_started()
        result = self.client.call_tool("kernel_output", {"kernel_ref": handle.kernel_ref}, timeout=60)
        return KaggleOutputResult(
            ok=True, log_text=result.get("log", ""), files=result.get("files", {}),
        )

    def cancel(self, handle: KaggleKernelHandle) -> bool:
        self._ensure_started()
        try:
            self.client.call_tool("kernel_cancel", {"kernel_ref": handle.kernel_ref}, timeout=30)
            return True
        except MCPError:
            return False

    def close(self) -> None:
        if self._started:
            self.client.stop()
            self._started = False
