# MCP (Model Context Protocol) Integration

The harness uses MCP in two distinct ways, which must not be confused:

1. **Local built-in tools, served as MCP** — so any MCP-capable client
   (including this harness itself, or a third-party IDE) can use the same
   `read`/`glob`/`grep`/`patch`/`shell`/`todo`/`memory`/`skills` tools.
2. **Remote provider bridges** — `colab-mcp` and `kaggle-mcp` are each
   wrapped so the harness's `ColabDriver`/`KaggleDriver` can reach the
   actual remote GPU backend. **These two differ fundamentally in their
   integration model** and are implemented separately, not treated as
   symmetric.

## Local built-in stdio MCP server

`openagent.mcp.stdio_builtin.serve()` implements a minimal newline-delimited
JSON-RPC 2.0 server over stdio (`initialize`, `tools/list`, `tools/call`):

```bash
python -m openagent.mcp.stdio_builtin
```

`openagent.mcp.manager.MCPManager` is the harness-side client/validator:
it refuses to start any server with `public_endpoint=True`
(`MCPServerSpec.public_endpoint`), and `validate_server()` runs a full
lifecycle check — startup, `tools/list`, a real `tools/call`, a timeout
test, and workspace-containment — before a server is trusted
(`tests/test_mcp.py` exercises all of this against
`tests/fixtures/fake_mcp_server.py`).

```bash
openagent mcp list     # the harness's own builtin tool list, MCP-shaped
```

## Colab MCP (`googlecolab/colab-mcp`)

**Implemented first**, per project priority.

Real integration model (confirmed from the project's own README): colab-mcp
is installed as a local stdio server (`uvx git+https://github.com/googlecolab/colab-mcp`)
by an MCP-capable client that supports `notifications/tools/list_changed`
(e.g. Gemini CLI, Claude Code, Windsurf), and it **bridges to a Colab
notebook that is already open in your browser**. There is no independent
network path into the Colab runtime — everything happens by sending
code-execution requests through this bridge into the open notebook and
reading results back over the same channel.

`openagent.mcp.servers.colab_mcp.ColabMcpExecClient`:

- Discovers the actual code-exec tool name at startup via `tools/list`
  (checking `execute_cell` / `run_cell` / `execute_code` / `run_code`,
  since colab-mcp's exact tool surface may evolve) rather than hardcoding
  one — if none is found, it raises a clear `MCPError` instead of silently
  no-op'ing.
- Implements the small `execute(code) -> ColabExecResult` protocol that
  `openagent.providers.colab.ColabDriver` expects, so the rest of the
  harness never has to know about MCP JSON-RPC framing.
- Wraps any underlying `MCPError` as a failed `ColabExecResult` rather than
  propagating an exception out of a provider lifecycle call.

This drives `ColabDriver.start()`'s design: it **requires** an injected
`exec_client` and raises a `ProviderError` without one — there's no
fallback path that tries to reach Colab over the open internet.

## Kaggle MCP (`Galaxy-Dawn/kaggle-mcp`)

**Implemented second**, after Colab, per project priority.

Real integration model (confirmed from the project's own README): this is
a **community** (non-official) local stdio server wrapping the Kaggle REST
API — 51 tools across competitions/datasets/kernels/models/benchmarks, plus
10 discussion-search tools the *official* Kaggle MCP
(`https://www.kaggle.com/mcp`, OAuth2, remote) lacks. Installed via
`uvx kaggle-mcp-server`, authenticated with `KAGGLE_API_TOKEN` or
`~/.kaggle/kaggle.json`. Unlike colab-mcp, **it has no live two-way
code-exec channel into a running kernel** — it is a batch wrapper around
push-kernel / poll-status / read-output.

`openagent.mcp.servers.kaggle_mcp.KaggleMcpExecClient` implements
`openagent.providers.kaggle.KaggleExecClient` as:

- `push_kernel(dir)` → calls the `push_kernel` tool, returns a
  `KaggleKernelHandle`.
- `get_status(handle)` → calls `kernel_status`, returns a
  `KaggleStatusResult`.
- `get_output(handle)` → calls `kernel_output`, returns logs + output
  files.
- `cancel(handle)` → best-effort; returns `False` rather than raising if
  the underlying call fails.

`KaggleDriver` is built around this push→poll→read pattern — it never
assumes interactive exec parity with Colab. Prefer **same-container
execution**: run the actual work (download, checksum, launch
`llama-server`) inside the pushed kernel itself, and use `get_status`/
`get_output` purely for progress/health polling, not as a remote shell.

## Why the two aren't symmetric

| | colab-mcp | kaggle-mcp |
|---|---|---|
| Channel | live bridge into an already-open notebook | batch REST wrapper over pushed kernels |
| Exec model | call a cell-execution tool, read results back interactively | push a kernel, poll `kernel_status`, read `kernel_output` once complete |
| Official vs. community | official Google project | community project (the *official* Kaggle MCP is remote/OAuth2 and lacks kernel push/poll tools) |
| Failure mode if misused | tool not found → `MCPError` (no silent no-op) | `push_kernel` with no returned ref → `MCPError` |

Both adapters are validated the same way the local builtin server is:
startup, `tools/list`-equivalent discovery, a real tool call, and
graceful failure handling — see `tests/test_mcp_provider_adapters.py`.
