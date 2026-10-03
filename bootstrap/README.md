# Bootstrap artifacts (reference examples)

The files under `colab/` and `kaggle/` in this directory are a **checked-in
reference example** of what `openagent providers bootstrap <provider>
<model-id>` actually generates for the default model
(`qwen3.8-27b-gguf-q4km`). They contain no secrets, no model weights, and
no account-specific values beyond an obvious `your_kaggle_username`
placeholder in `kaggle/kernel-metadata.json` — they're safe to commit and
are meant purely to show reviewers (and you) what the generator produces
without having to run it first.

**Do not hand-edit these for real use.** Regenerate them for your actual
target model/session instead, so the pinned llama.cpp release, model
sha256, and runtime flags always match the current
`openagent/models/registry.yaml`:

```bash
openagent providers bootstrap colab  <model-id> --out-dir ./bootstrap/colab
openagent providers bootstrap kaggle <model-id> --out-dir ./bootstrap/kaggle
```

- `colab/*.ipynb` + `colab/*.sh` — a Colab notebook and an equivalent plain
  shell script: install the pinned llama.cpp CUDA build, download +
  checksum-verify the model, launch `llama-server` on loopback, and run an
  in-notebook health check. Run these *inside* the Colab notebook you
  intend to drive via `colab-mcp` — see [docs/mcp.md](../docs/mcp.md).
- `kaggle/kernel-metadata.json` + `kaggle/kernel.py` — a pushable Kaggle
  kernel: same install/download/launch/health-check steps, packaged as a
  script kernel you push via `kaggle-mcp` (or the Kaggle CLI directly) and
  poll for completion — see [docs/provider-limits.md](../docs/provider-limits.md#kaggle).

See [docs/install.md](../docs/install.md) for the end-to-end setup flow
these fit into.
