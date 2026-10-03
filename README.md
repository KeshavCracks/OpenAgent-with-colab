# OpenAgent Harness

A downloadable, GitHub-ready local AI agent harness. It gives you a
DeepSeek-Harness-style developer experience — sessions, a file/patch/shell
tool loop, trajectory inspection, tool-call details, subagents, scheduled
tasks, and developer observability — while running on a low-RAM local
machine and delegating heavy LLM inference to a short-lived **remote** GPU
backend (Google Colab first, Kaggle second).

> This project reimplements the *reference UX/architecture pattern*
> popularised by DeepSeek's local harness tooling. It contains no
> proprietary branding, code, or weights from that or any other project.

## Why this split?

| Runs locally (your low-RAM PC)                         | Runs remotely (free Colab/Kaggle GPU)            |
|----------------------------------------------------------|---------------------------------------------------|
| CLI / optional web UI                                     | `llama-server` (OpenAI-compatible, loopback-only)  |
| Agent loop, tool dispatch, orchestration (planner/worker/reviewer) | The one resident large LLM (Q4/Q5 GGUF)   |
| File, patch, shell-with-timeout, todo tools               | Short-lived, authenticated access only — never a public endpoint |
| Skill registry + finder, memory store, research/browser modules | — |
| Model registry, checksum verification, bootstrap generation | — |
| Trajectory log, benchmark harness, security scanners       | — |

No model weights are ever bundled in this repository, and no real secret
(API key, token, cookie, password) is ever committed — configuration only
ever contains `env:VAR_NAME` / `keyring:service:key` references or the
literal placeholder `CHANGE_ME` (enforced by `openagent.config` at load
time; see [docs/security.md](docs/security.md)).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 1. Inspect the model registry (no downloads, no network calls)
openagent models list
openagent models show qwen3.8-27b-gguf-q4km

# 2. Create a local-workspace session
openagent new --workspace .

# 3. Generate a pinned Colab bootstrap (notebook + shell script) for the
#    default model -- nothing is executed yet, this only writes files
openagent providers bootstrap colab qwen3.8-27b-gguf-q4km --out-dir ./bootstrap/colab

# 4. Once you've run the bootstrap in an actual Colab notebook and have an
#    OpenAI-compatible llama-server reachable through your MCP bridge /
#    tunnel, point the harness at it and check its health
openagent providers bootstrap kaggle qwen3.8-27b-gguf-q4km --out-dir ./bootstrap/kaggle

# 5. Everything else (skills, memory, security scans, benchmarks) works
#    fully offline, with no model required:
openagent skills find "review this diff for hardcoded secrets"
openagent security secret-scan .
openagent benchmark run --model-id qwen3.8-27b-gguf-q4km
```

See [docs/install.md](docs/install.md) for a from-scratch setup walkthrough
and [docs/session-lifecycle.md](docs/session-lifecycle.md) for the full
`new → status → checkpoint → stop` flow, including remote provider sessions.

## Architecture at a glance

```
┌─────────────────────────── local PC (low RAM) ───────────────────────────┐
│  CLI (openagent ...)        optional web UI (static, read-only views)    │
│       │                                                                   │
│       ▼                                                                   │
│  Agent loop  ──tool calls──▶  Tool registry (read/glob/grep/patch/shell/  │
│    │    │                     todo/memory/skills) ── WorkspaceGuard       │
│    │    └─ Orchestration (planner → worker → reviewer, budgets, retries,  │
│    │       rollback)                                                      │
│    ├─ Context system (OpenVikingContext: ranked, redacted, budgeted)      │
│    ├─ Memory store (provenance + TTL + secret-refusal, sqlite)            │
│    ├─ Skill registry + finder (progressive disclosure)                    │
│    ├─ Research (Agent-Reach: lawful search/RSS/GitHub/YouTube/docs)       │
│    ├─ Browser automation (approval-gated for sensitive actions)           │
│    ├─ Security module (secret scan / dep audit / auth review — defensive)│
│    ├─ Diagram-as-code (Mermaid)                                           │
│    ├─ Benchmark harness                                                   │
│    ├─ Model registry + checksum verification + bootstrap generators      │
│    ├─ Model router (switches resident model by task phase, not per call) │
│    ├─ Local stdio MCP server (same built-in tools, MCP-shaped)            │
│    └─ Provider drivers: Colab (colab-mcp bridge) → Kaggle (kaggle-mcp)    │
└────────────────────────────────┬──────────────────────────────────────────┘
                                  │ short-lived, authenticated access only
                                  ▼
                 ┌────────────────────────────────────┐
                 │  Remote GPU container (Colab/Kaggle) │
                 │  llama.cpp llama-server (loopback)   │
                 │  pinned CUDA build, one resident LLM │
                 └────────────────────────────────────┘
```

Two operating modes (see [docs/session-lifecycle.md](docs/session-lifecycle.md)):

* **`local-workspace-remote-inference`** (default) — your files and the
  agent loop live on your machine; only chat/completions calls cross the
  wire to the remote `llama-server`.
* **`remote-workspace-remote-execution`** (advanced) — workspace and shell
  execution also happen inside the remote container (e.g. because the repo
  under test is large, or you want Colab's disk/CPU). Opt-in only.

## What's implemented

- **CLI** (`openagent.cli`) covering sessions, models, provider bootstrap,
  MCP, skills, memory, research doctor, security scans, benchmarks,
  scheduled tasks, and trajectory inspection. Run `openagent --help` or see
  [docs/troubleshooting.md](docs/troubleshooting.md) for a full command
  reference.
- **Agent loop** (`openagent.agent.loop`) with pluggable LLM client, tool
  dispatch, trajectory recording, and max-iteration/max-tool-call guards.
- **Orchestration** (`openagent.orchestration`) — budgets (tool-call/token/
  wall-clock) and a planner → worker → reviewer pattern with retries and
  rollback, in the spirit of the "Awesome Harness Engineering" patterns.
- **Tools** (`openagent.tools`) — `read`, `glob`, `grep`, `patch` (atomic
  multi-file unified-diff application), `shell` (timeout-enforced,
  workspace-contained), `todo`, `memory`, `skills` — all routed through a
  single `WorkspaceGuard` containment/deny-list boundary.
- **Model registry** (`openagent/models/registry.yaml`) — pinned
  repo/revision/file/sha256/size/VRAM-RAM/context/license/tool-template per
  model; see [docs/model-selection.md](docs/model-selection.md) for the
  full rationale on each entry (Qwen3.8-27B default, OrcaSAQ-2 community/
  gated, DeepHat specialist, Cloudflare Clef router-only).
- **Runtime** (`openagent.runtime`) — pinned llama.cpp install script
  generation, OpenAI-compatible health checks (models endpoint, chat
  completion, grammar-constrained tool call), and a model router that
  switches the one resident large LLM by task phase.
- **Providers** (`openagent.providers`) — Colab first, then Kaggle, plus a
  "bring your own endpoint" local driver; each implements
  detect-GPU/generate-bootstrap/start/status/checkpoint/stop against a
  shared `ProviderDriver` interface.
- **MCP** (`openagent.mcp`) — a local stdio MCP server exposing the
  built-in tools, plus adapters for the real `googlecolab/colab-mcp` and
  `Galaxy-Dawn/kaggle-mcp` projects (these differ in integration model —
  see [docs/mcp.md](docs/mcp.md)).
- **Skills** (`openagent.skills`) — a pinned-revision catalog with
  progressive disclosure (lightweight summary vs. full body) and a
  trigger-matching finder.
- **Research / browser** (`openagent.research`, `openagent.browser`) —
  Agent-Reach-style lawful public research channels with a `doctor`
  command, and an approval-gated browser-automation session for sensitive
  actions.
- **Memory** (`openagent.memory`) — scoped, TTL'd, provenance-tracked
  key/value memory with hard secret-refusal.
- **Context system** (`openagent.context_system`) — OpenVikingContext:
  ranked, redacted, budgeted, provenance-tracked access across sources.
- **Diagram-as-code** (`openagent.diagram`) — versioned Mermaid diagrams
  (architecture, sequence, threat model, agent trace).
- **Security** (`openagent.security`) — defensive-only secret scanning,
  dependency auditing, and auth-code review.
- **Benchmark harness** (`openagent.benchmark`) — a small offline suite plus
  cross-model comparison, used as the acceptance gate for promoting any
  model to primary.
- **Subagents & scheduler** (`openagent.agent.subagents`,
  `openagent.agent.scheduler`) — restricted-tool-set child sessions, and a
  cron-like local task store driven by `openagent schedule tick`.

## Acceptance gates

A model or change is **not** considered production-ready for this harness
until it clears all of:

1. Correct provider/GPU detection for its target backend.
2. Checksum-verified model loading (sha256 pinned in the registry).
3. A healthy OpenAI-compatible endpoint (`/v1/models` + tool-call-capable
   `/v1/chat/completions`).
4. Valid single- and multi-step tool calls through the agent loop.
5. Patch-based editing without corruption (atomic, all-or-nothing).
6. Time-limited shell/test execution, properly contained to the workspace.
7. Context budgeting and summarization under long trajectories.
8. A successful multi-file coding task end to end.
9. A lawful research/browser task that returns real, resolvable citations.
10. Persistent memory recall that never leaks a secret.
11. Skill discovery that picks the correct skill for a task description.
12. Benchmark comparisons across candidate models.
13. Clean stop with artifact (trajectory/checkpoint) preservation.

Any model — including a technically "working" chat model — is **rejected
as primary** if it fails the tool-reliability, latency, safety, or
licensing/benchmark gates. See `gate_passed` in
`openagent/models/registry.yaml` and
[docs/model-selection.md](docs/model-selection.md).

## Documentation

- [docs/install.md](docs/install.md) — from-scratch setup
- [docs/configuration.md](docs/configuration.md) — `config/default.yaml` and `.env` reference
- [docs/model-selection.md](docs/model-selection.md) — registry, gating, ramp-up procedure
- [docs/session-lifecycle.md](docs/session-lifecycle.md) — modes, new/status/checkpoint/stop, subagents
- [docs/provider-limits.md](docs/provider-limits.md) — Colab/Kaggle free-tier limits and forbidden patterns
- [docs/mcp.md](docs/mcp.md) — colab-mcp vs kaggle-mcp integration models
- [docs/security.md](docs/security.md) — secrets policy, defensive security module
- [docs/licensing.md](docs/licensing.md) — per-component license summary
- [docs/diagrams.md](docs/diagrams.md) — diagram-as-code conventions
- [docs/research-skill-direction.md](docs/research-skill-direction.md) — scientific-agent-skill design note
- [docs/troubleshooting.md](docs/troubleshooting.md) — common failures and the CLI command reference

## Testing

```bash
pip install -e ".[dev]"
pytest -q                               # full suite (200+ tests, offline/fake-backed)
pytest -q --cov=openagent --cov-report=term-missing
```

The test suite never downloads model weights or talks to a real Colab/
Kaggle backend — providers, MCP servers, and HTTP health checks are all
exercised through injectable fakes so CI can run entirely offline.

## License

Apache-2.0 for harness code (see `pyproject.toml`). Third-party models,
skills, and reference projects keep their own licenses — see
[docs/licensing.md](docs/licensing.md) for the full per-component summary.
Never assume a third-party component is permissively licensed without
checking; several entries in this repo are explicitly marked
"license_verified: false" or "verify before relying" pending a human legal
read.
