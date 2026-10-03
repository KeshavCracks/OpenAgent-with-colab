# Licensing

This project redistributes **no third-party source code, model weights, or
skill bodies verbatim**. Every reference project below is either (a) a
pinned-revision conceptual/behavioral reference that this harness
reimplements its own code against, or (b) a model/weights repo the harness
downloads directly from the vendor at runtime (never bundled). Always
re-check the upstream license before relying on a specific entry in
production — several are explicitly marked unverified below.

## Harness code

Apache-2.0 (`pyproject.toml`). Applies to everything under `openagent/`,
`tests/`, and this documentation.

## Models (`openagent/models/registry.yaml`)

| Model | Declared license | Verified? |
|---|---|---|
| `qwen3.8-27b-bf16-official` / `qwen3.8-27b-gguf-q4km` / `qwen3.8-27b-gguf-q5km` / `qwen3.8-27b-mtp-draft` | Apache-2.0 | Yes |
| `orcasaq2-cyber-27b-uncensored` | Apache-2.0 (as declared in repo card) | **No** — re-audit required before production use; gated + `gate_passed: false` until then |
| `deephat-v1-7b-official` / `deephat-v1-7b-gguf-q4km` | Apache-2.0 + DeepHat extended usage restrictions | **No** — the extended-usage addendum needs a human legal read |
| `cloudflare-clef-27b` | Apache-2.0 | Yes |
| `nomic-embed-text-v1.5-gguf-q4km` | Apache-2.0 | Yes |

Models are **never bundled** in this repository — `openagent.models.download`
fetches them directly from Hugging Face at a pinned revision, checksum-
verifying against the sha256 recorded in the registry.

## Skill catalog (`openagent/skills/catalog/`)

| Skill | Modeled on | Declared license | Notes |
|---|---|---|---|
| `lifecycle-spec-plan-build-ship` | `addyosmani/agent-skills` (pinned commit `9d0c60d406b454a78ccc0a175b19932047aa4dac`) | MIT | |
| `packaged-skill-workflow` | `vercel-labs/agent-skills` (pinned commit `063bee94c3f4df8453406c830b0a7df0f2860278`) | **Unspecified upstream** | GitHub's API reported no detected LICENSE file at the pinned commit — treat as "all rights reserved by default." Only the *packaging pattern* (a `SKILL.md` + CLI) is reimplemented; nothing is vendored verbatim. Re-check before any redistribution. |
| `agent-reach-research` | `Panniantong/Agent-Reach` (pinned commit `a19a171fa980a0785849596492e0af4db800c82f`) | MIT | |
| `browser-use-workflow` | modeled on the `browser-use`/`browser-env` capability pattern | MIT, declared "verify before relying" | |
| `defensive-security-review` | Anthropic's published cybersecurity-skills guidance (defensive-only) | Apache-2.0 (harness-authored) | Guidance, not vendored code |
| `scientific-research-assistant` | harness-authored | Apache-2.0 | See [research-skill-direction.md](research-skill-direction.md) |
| `diagram-as-code` | harness-authored | Apache-2.0 | |

## MCP server adapters

| Project | Role | Declared license |
|---|---|---|
| `googlecolab/colab-mcp` | Colab exec bridge | Apache-2.0 |
| `Galaxy-Dawn/kaggle-mcp` | Kaggle kernel REST wrapper | MIT |

These are invoked as external processes (`uvx git+...` /
`uvx kaggle-mcp-server`) — their code is not vendored into this repo at
all; only a thin adapter (`openagent/mcp/servers/*.py`) speaking their
JSON-RPC surface is harness-authored.

## Other reference modules (no code vendored, pattern reimplemented)

- **Agent Memory**, **Orchestration (planner/worker/reviewer)**, **Context
  system (Open Viking pattern)**, **Benchmark harness** — harness-authored,
  Apache-2.0, inspired by publicly described design patterns rather than
  any single repository.

## Your responsibility

If you redistribute a build of this harness, or fine-tune/host one of the
non-Apache-2.0 models above, re-verify the exact license terms yourself —
this document summarizes what the registry/catalog metadata states as of
2026-10-03, it is not legal advice.
