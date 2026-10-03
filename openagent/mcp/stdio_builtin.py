"""Serve the harness's built-in tools (read/glob/grep/patch/shell/todo/
memory/skills) as a local stdio MCP server, so any MCP-capable client
(including this harness itself, or a third-party IDE integration) can use
them beside the agent loop -- "default to local stdio MCP servers running
beside the harness".

Run with: `python -m openagent.mcp.stdio_builtin`
"""
from __future__ import annotations

import json
import sys

from openagent.tools.base import ToolRegistry


def serve(registry: ToolRegistry, instream=sys.stdin, outstream=sys.stdout) -> None:
    for line in instream:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})
        response: dict = {"jsonrpc": "2.0", "id": req_id}
        try:
            if method == "initialize":
                response["result"] = {"serverInfo": {"name": "openagent-builtin", "version": "0.1.0"}}
            elif method == "tools/list":
                response["result"] = {"tools": [s["function"] for s in registry.schemas()]}
            elif method == "tools/call":
                name = params["name"]
                arguments = params.get("arguments", {})
                record = registry.dispatch(name, arguments)
                if record.ok:
                    response["result"] = {"output": record.result}
                else:
                    response["error"] = {"code": -32000, "message": record.error}
            else:
                response["error"] = {"code": -32601, "message": f"Unknown method: {method}"}
        except Exception as exc:  # noqa: BLE001
            response["error"] = {"code": -32000, "message": str(exc)}
        outstream.write(json.dumps(response) + "\n")
        outstream.flush()


if __name__ == "__main__":  # pragma: no cover
    from openagent.agent.builtin_tools import build_default_tool_registry
    from openagent.tools.base import WorkspaceGuard
    from pathlib import Path

    guard = WorkspaceGuard(root=Path.cwd())
    serve(build_default_tool_registry(guard))
