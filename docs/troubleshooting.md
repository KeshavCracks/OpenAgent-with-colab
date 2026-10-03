# Troubleshooting & CLI Reference

## Full command reference

```
openagent --version

openagent new --workspace <path> [--mode local-workspace-remote-inference|remote-workspace-remote-execution]
openagent sessions
openagent status <session_id>
openagent stop <session_id>
openagent checkpoint <session_id> [--label <text>]

openagent models list
openagent models show <model_id>
openagent models verify <model_id> <path-to-file>

openagent providers bootstrap colab|kaggle <model_id> [--out-dir <dir>]

openagent mcp list

openagent skills list
openagent skills show <name>
openagent skills find "<task description>" [--top-k N]

openagent memory remember <scope> <key> <value>
openagent memory recall <scope> [key]
openagent memory search <scope> <query>
openagent memory forget <record_id>

openagent research doctor

openagent security secret-scan [path]
openagent security dep-audit [path] [--ecosystem python|node]

openagent benchmark run [--model-id <id>]

openagent schedule add <name> <interval_seconds> <action>
openagent schedule list
openagent schedule tick

openagent trajectory show <session_id> [--tool-calls-only]
```

Every subcommand prints JSON to stdout (so it's scriptable) and uses a
non-zero exit code to signal failure (e.g. `security secret-scan` exits `1`
if it finds anything, `models verify` exits `1` on a checksum mismatch,
`memory remember` exits `3` if the value looks like a secret).

## Common issues

### `openagent memory remember ...` exits 3 / prints `REFUSED: ...`

The value you passed looks like a secret (API key, token, etc.) by pattern
match. This is intentional — memory is for durable *facts*
("this repo uses pytest"), never credentials. Store real secrets in `.env`
or your OS keyring instead; see [security.md](security.md).

### `openagent models verify <id> <path>` reports `ok: false`

The downloaded file's sha256 doesn't match the pinned value in
`openagent/models/registry.yaml`. **Do not use the file** — re-download it.
A changed hash at the same filename/revision is treated as a supply-chain
signal, not noise.

### `openagent providers bootstrap <provider> <model_id>` fails with "no pinned sha256"

The target model entry in the registry has `source.sha256: null` (e.g. the
official BF16 Qwen3.8-27B entry, which ships as multi-shard safetensors
with a Hub manifest instead of a single pinned file hash). Use one of the
GGUF entries instead — see [model-selection.md](model-selection.md).

### Colab/Kaggle driver `start()` raises `ProviderError: ... requires an exec_client`

You must inject a real `exec_client` (a `ColabMcpExecClient` /
`KaggleMcpExecClient`, or a test double implementing the same protocol)
before calling `start()`. There's no implicit network path to either
backend — see [mcp.md](mcp.md).

### `run_preflight` / `check_server_health` reports `reachable: False`

The configured `llama-server` base URL isn't actually reachable from where
the harness process is running. Common causes: the remote notebook/kernel
hasn't actually started the server yet, the tunnel/bridge has expired
(`runtime.tunnel.ttl_minutes`), or you're pointing at a public address
instead of the authenticated loopback/tunnel endpoint (which this harness
refuses to do on your behalf).

### `QuotaExceededError` from a provider driver

The session exceeded `max_session_hours` for that provider
(`ProviderLimits.max_session_hours`, 12h for both Colab and Kaggle by
default). Checkpoint, stop, and start a fresh session — this is a hard
guardrail against quota evasion, not a bug.

### `openagent security secret-scan` false-positives on a placeholder

Placeholders must follow the `env:`/`keyring:`/`CHANGE_ME`/`REPLACE_ME`
convention recognized by `generic_assignment` in
`openagent/security/secret_scan.py`. If you introduce a new placeholder
convention in `config/default.yaml`, add it to that pattern's exclusion
list too, or the scanner (correctly) treats it as suspicious.

### Tests fail / behave differently across a full `pytest -q` run

They shouldn't — every provider, MCP server, and HTTP health check in the
test suite is exercised through injectable fakes specifically so the suite
can run fully offline and order-independently. If you see cross-file
interference, check for a test that forgot to use `tmp_path`/`monkeypatch`
for `HOME`, `~/.openagent/...`, or `config/default.yaml` state instead of a
temp directory.

## Where logs and state live

- Sessions: `~/.openagent/sessions/<id>.json`
- Trajectories: `~/.openagent/trajectories/<id>.jsonl`
- Memory: `~/.openagent/memory/memory.sqlite3`
- Scheduled tasks: `~/.openagent/schedule.json`
- Logs: `~/.openagent/logs` (configurable via `logging.dir`)

None of these paths are ever created inside the git repository itself
(see `.gitignore`), so `git status` stays clean during normal use.
