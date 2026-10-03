# Configuration

The harness reads `config/default.yaml` (checked into git — placeholders
only) layered with environment variables from `.env` (gitignored, real
secrets live here, see [security.md](security.md)). Load it in code via
`openagent.config.Config.load()`.

## Top-level sections (`config/default.yaml`)

| Section | Purpose |
|---|---|
| `mode` | `local-workspace-remote-inference` (default) or `remote-workspace-remote-execution` (advanced) — see [session-lifecycle.md](session-lifecycle.md). |
| `harness` | `low_ram_mode` (always true — never load weights locally), `max_context_tokens`, `context_budget` (soft/hard limits + summarize-when-over). |
| `workspace` | `root` containment boundary and `deny_paths` for `WorkspaceGuard` (every file/shell tool is routed through this). |
| `providers` | Per-backend `enabled`, credential references (`env:...`), and `limits` (session hours, VRAM/RAM/disk, GPU, CPU cores, weekly quota, `public_inbound_address: false`). See [provider-limits.md](provider-limits.md). |
| `runtime` | llama.cpp server bind/port/context/KV-cache/flash-attention/parallel-slots, bearer-token auth, and tunnel mode/TTL. |
| `models` | `default` model id and `registry_path` pointing at `openagent/models/registry.yaml`. |
| `mcp` | `builtin_stdio`, provider order, and `allow_public_endpoints: false` (hard-enforced in code, not just config). |
| `memory` | sqlite backend path, default TTL, `redact_secrets: true`. |
| `skills` | catalog path, max per-skill context budget, and pinned external skill sources. |
| `research` | Agent-Reach repo/pin, login-gated platform list, and the "require a user-owned session for gated platforms" flag. |
| `browser` | disabled by default; `require_approval_for` lists the sensitive action types that need explicit approval. |
| `logging` | level and local log directory. |

## Secret references

Every credential-shaped field in `config/default.yaml` must be one of:

- `env:VAR_NAME` — read from the process environment (populate via `.env`,
  CI secrets, or your shell).
- `keyring:service:key` — read from the OS keyring (requires the `keyring`
  extra).
- `CHANGE_ME` — explicit placeholder, resolves to "not configured" rather
  than failing.

`openagent.config.resolve_secret()` is the only sanctioned way to turn one
of these references into an actual value at runtime, and
`validate_no_literal_secrets()` scans config text for anything that looks
like a real token/key pattern and refuses to load it. This is covered by
`tests/test_config_secrets.py`.

## Per-session overrides

`openagent new --workspace <path> --mode <mode>` creates a session whose
metadata (workspace root, mode, provider, model, status) is stored under
`~/.openagent/sessions/<id>.json` — independent of `config/default.yaml`,
so you can run multiple sessions with different workspaces/modes
concurrently. See `openagent.agent.session.SessionStore`.

## Model registry

`openagent/models/registry.yaml` is a separate, heavily-annotated file
(schema documented inline) — see [model-selection.md](model-selection.md)
rather than duplicating its structure here.
