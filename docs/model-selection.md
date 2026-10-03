# Model Selection

The model registry lives at `openagent/models/registry.yaml` and is loaded
via `openagent.models.registry.load_registry()`. Every entry was checked
against the Hugging Face Hub file-metadata API on 2026-10-03 — repo id,
pinned revision (commit sha, never a mutable branch), exact filename, and
sha256 come directly from the Hub, not estimates.

```bash
openagent models list              # id / status / role / gate_passed / license for every entry
openagent models show <model-id>   # full registry record
openagent models verify <model-id> <path-to-downloaded-file>   # sha256 check
```

## The registry

| id | role(s) | status | params | license | notes |
|---|---|---|---|---|---|
| `qwen3.8-27b-bf16-official` | planner, reviewer | `reference_only` | 27B | Apache-2.0 | Authoritative upstream BF16 weights; too large for free Colab/Kaggle GPUs — use a GGUF derivative to actually run it. |
| `qwen3.8-27b-gguf-q4km` | planner, executor, reviewer | **`available` — DEFAULT** | 27B | Apache-2.0 | Community Q4_K_M requantization of the official weights (`unsloth/Qwen3.8-27B-GGUF`). Fits a single free Colab/Kaggle T4 at 8K context, q8 KV cache, text-only. |
| `qwen3.8-27b-gguf-q5km` | planner, reviewer | `available` | 27B | Apache-2.0 | Same base weights, Q5_K_M. Needs ~22GB VRAM — doesn't fit a single free Colab T4, fits Kaggle's dual-T4 pool. Use when VRAM allows, per the "Q5 if VRAM allows" rule. |
| `qwen3.8-27b-mtp-draft` | speculative_draft | `available` | — | Apache-2.0 | Optional MTP speculative-decoding draft head. Enable only after text-only tool-call reliability is already measured on the base model. |
| `orcasaq2-cyber-27b-uncensored` | executor (candidate) | `gated`, **`gate_passed: false`** | 27B | Apache-2.0 (declared, not re-audited) | Third-party community GGUF (`orcarouter/OrcaSAQ-2-Cyber-27B-Uncensored-GGUF`), requires an authenticated, license-accepted HF token. **"Uncensored" is never treated as license to bypass this harness's safety/legal/platform policy.** Stays gated until it independently passes license re-audit, local safety review, tool-call-reliability benchmarking, and a head-to-head benchmark against the default Qwen3.8 GGUF. |
| `deephat-v1-7b-official` | executor (specialist) | `available` | 7.6B | Apache-2.0 + DeepHat extended usage restrictions (needs human legal read) | The **only** model actually published under the `DeepHat` org as of 2026-10-03 — a cybersecurity/DevOps-tuned finetune of `Qwen2.5-Coder-7B`, **not** a Qwen3.8-derived model. Registered as an optional specialist, never a drop-in default replacement. |
| `deephat-v1-7b-gguf-q4km` | executor | `available` | 7.6B | Apache-2.0 | Runnable llama.cpp quant of the above (`mradermacher/DeepHat-V1-7B-GGUF`). Small footprint; only keep resident alongside a planner if VRAM is explicitly budgeted. |
| `cloudflare-clef-27b` | **decision_router only** | `available` | 27B | Apache-2.0 | `Cloudflare/clef`. Prefill-only, returns calibrated probabilities over a caller-defined schema — it does **not** generate free-form text and **must never** be registered as a general coding/chat backend. Only reachable through `openagent.runtime.router`, with its own schema validation and hardware budget. |
| `nomic-embed-text-v1.5-gguf-q4km` | embedding | `available` | — | Apache-2.0 | ~85MB; safe to keep resident alongside a large planner/executor for retrieval/memory search. |

## `gate_passed` — the promotion gate

Every entry starts with `gate_passed: false` and a `verification` block of
individually-false checklist items (`checksum_verified_locally`,
`server_health_checked`, `tool_call_reliability_tested`,
`safety_reviewed`, `latency_profiled`, plus model-specific items like
`license_reaudited` or `schema_validation_tested`). A model only flips to
`gate_passed: true` after **all** relevant checks for that model have
actually been run and recorded against its exact pinned sha256 — not
"vendor claims it's good." `benchmark_status` stays
`vendor_claims_unverified` until a local benchmark run
(`openagent benchmark run`) records real, reproduced numbers.

**Qwen3.8-27B GGUF Q4_K_M remains the default/primary model until/unless a
candidate (e.g. OrcaSAQ-2) independently clears every one of these gates.**
A model that "chats fine" but fails tool-reliability, latency, safety, or
licensing checks is rejected as primary regardless of how capable it looks
in casual use.

## Ramp-up procedure (applies to any new GGUF model)

1. Download + checksum-verify (`openagent.models.download.download_model`,
   never trust a filename alone).
2. Install the pinned llama.cpp CUDA build
   (`generate_llama_cpp_install_script`, pinned release tag — never
   `latest`).
3. Start the server **text-only**, 8K context, q8 KV cache, a single
   parallel slot.
4. Run `openagent.runtime.health.run_preflight` (GPU/VRAM/RAM/disk,
   checksum, server health, a real tool-call round-trip).
5. Run the benchmark suite and tool-reliability tests before expanding
   context length, enabling vision/MTP, or adding parallel slots — changing
   more than one variable at a time confounds latency measurements.
6. Only after steps 1-5 pass should `verification.*` fields be flipped to
   `true` and `gate_passed` reconsidered.

## Multi-model roles and switching

The harness keeps **one large LLM resident at a time** on the (free,
VRAM-constrained) remote GPU, and switches which model is resident **by
task phase** (`plan → execute → review`, `embed`, `route`), never per
individual tool call — see `openagent.runtime.router.ModelRouter`. A small
embedding model may stay resident alongside the large one if the combined
footprint fits the configured VRAM budget; loading a new *large* model
always evicts the previous large one first.
