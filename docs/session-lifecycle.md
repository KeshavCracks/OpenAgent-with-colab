# Session Lifecycle

## Modes

Set per-session via `openagent new --mode <mode>`, defaulting to the value
in `config/default.yaml` (`local-workspace-remote-inference`):

- **`local-workspace-remote-inference`** (default) — your files, the agent
  loop, tools, skills, memory, and trajectory all live on your local
  machine. Only `/v1/chat/completions`-style calls cross the wire to the
  remote `llama-server`. This is the right mode for almost everything.
- **`remote-workspace-remote-execution`** (advanced, opt-in) — the
  workspace and shell execution also happen inside the remote Colab/Kaggle
  container (e.g. the repo under test is large, or you want to use the
  remote machine's disk/CPU as well as its GPU). Still never exposes a
  public inbound endpoint; access stays short-lived and authenticated
  through the same MCP bridge.

## The core CLI flow

```bash
openagent new --workspace /path/to/project --mode local-workspace-remote-inference
# -> {"session_id": "...", "status": "created", ...}

openagent sessions                 # list all local sessions
openagent status <session_id>      # show one session's metadata
openagent checkpoint <session_id> --label "before refactor"
openagent stop <session_id>        # status -> "stopped"
```

Session metadata (`openagent.agent.session.SessionMeta`) is stored as one
JSON file per session under `~/.openagent/sessions/<id>.json`: workspace
root, mode, provider, model id, status (`created | running | stopped |
expired | failed`), and — for subagents — `parent_session_id`.

## Trajectory inspection and tool-call details

Every agent-loop run appends newline-delimited JSON events (`message`,
`tool_call`, `phase_switch`) to `~/.openagent/trajectories/<session_id>.jsonl`
via `openagent.agent.trajectory.TrajectoryRecorder`.

```bash
openagent trajectory show <session_id>                  # summary: event/message/tool-call
                                                          # counts, error count, per-tool
                                                          # breakdown, total tool duration,
                                                          # phase switches
openagent trajectory show <session_id> --tool-calls-only  # full detail on every tool call:
                                                            # arguments, result, ok/error,
                                                            # duration_ms
```

## Subagents

`openagent.agent.subagents.SubagentManager.spawn()` creates an isolated
child session (own `session_id`, `parent_session_id` set, own trajectory
file) with a **restricted** tool registry
(`RestrictedToolRegistry(allowed_tools=...)`) for a bounded subtask — e.g.
"research this API and summarize" with only `read`/`grep` allowed. The
subagent's result (`ok`, `summary`, `tool_call_count`, `duration_seconds`)
is reported back into the parent's trajectory via `phase_switch` events
(`subagent_start` / `subagent_end`). A subagent attempting a disallowed
tool gets a `PermissionError`, not silent denial.

## Scheduled tasks

`openagent.agent.scheduler` is deliberately **not** a daemon — it stores
task definitions and decides *when* they're due; you drive it from cron,
systemd timers, or Windows Task Scheduler, keeping the harness's own local
footprint at zero background processes:

```bash
openagent schedule add nightly-tests 86400 "shell:pytest -q"
openagent schedule list
openagent schedule tick     # run every currently-due task once, then reschedule it
```

## Provider sessions (remote GPU backends)

A `ProviderSession` (`openagent.providers.base`) tracks: `provider`,
`session_id`, `state` (`NOT_STARTED | BOOTSTRAPPING | RUNNING | DEGRADED |
STOPPED`), `started_at`, `model_id`, a list of `HealthCheck`s, and a list of
checkpoints. Every provider driver (`LocalDriver`, `ColabDriver`,
`KaggleDriver`) implements the same five-method interface:

| Method | Purpose |
|---|---|
| `detect_gpu()` | Report the actual GPU/VRAM/RAM/CPU/disk shape available. |
| `generate_bootstrap(model, out_dir)` | Write pinned notebook/script files — no execution. |
| `start(model, session)` | Bootstrap + launch `llama-server` on the remote backend. |
| `status(session)` | Run health checks (reachability, `/v1/models`, chat completion, a real tool call). |
| `checkpoint(session, label)` | Record a labeled checkpoint (for crash/quota-limit recovery). |
| `stop(session)` | Clean shutdown; never leaves a public endpoint running. |

See [provider-limits.md](provider-limits.md) for the concrete Colab/Kaggle
free-tier numbers these drivers are built against, and
[mcp.md](mcp.md) for how `start()`/`status()` actually reach the remote
runtime (colab-mcp's live exec bridge vs. kaggle-mcp's push/poll kernel
model — these are **not** symmetric).

## Clean stop and artifact preservation

`stop()` always transitions the session to `STOPPED` and leaves the
trajectory file, session metadata, and any checkpoints in place under
`~/.openagent/` — nothing about shutting down a session deletes your
history. Only the remote GPU process/container is torn down.
