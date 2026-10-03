#!/usr/bin/env python3
"""A tiny fake stdio MCP server used to validate MCPManager/StdioMCPClient
lifecycle handling: startup, tool-list, a tool that hangs (timeout test),
and an unknown-method failure path."""
import json
import sys
import time


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params", {})
        response = {"jsonrpc": "2.0", "id": req_id}

        if method == "initialize":
            response["result"] = {"serverInfo": {"name": "fake-mcp", "version": "0.0.1"}}
        elif method == "tools/list":
            response["result"] = {"tools": [{"name": "echo", "description": "echo back arguments",
                                              "parameters": {"type": "object"}}]}
        elif method == "tools/call":
            name = params.get("name")
            if name == "slow_tool":
                time.sleep(5)  # longer than the client's short test timeout
                response["result"] = {"output": "too late"}
            elif name == "echo":
                response["result"] = {"output": params.get("arguments", {})}
            else:
                response["error"] = {"code": -32601, "message": f"Unknown tool: {name}"}
        else:
            response["error"] = {"code": -32601, "message": f"Unknown method: {method}"}

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
