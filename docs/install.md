# Install

## Requirements

- Python 3.10+
- A local machine with modest RAM (the harness never loads model weights
  locally — see `harness.low_ram_mode` in `config/default.yaml`).
- A free Google account for the Colab backend (implemented first). A free
  Kaggle account for the Kaggle backend (implemented second).
- `git`, and `curl`/`unzip` on whatever machine will actually *run*
  `llama-server` (that's the remote Colab/Kaggle container, not your local
  machine).

## 1. Clone and install the harness

```bash
git clone <this-repo-url>
cd OpenAgent-with-colab
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Optional extras:

```bash
pip install -e ".[browser]"   # Playwright, for openagent.browser.browser_use
pip install -e ".[keyring]"   # OS keyring backend for secret storage
pip install -e ".[all]"       # everything
```

## 2. Configure secrets (never in git)

Copy the example env file and fill in only what you need:

```bash
cp .env.example .env     # .env is gitignored; .env.example is the only
                          # secret-shaped file allowed in version control
```

`config/default.yaml` is checked into git and must only ever contain
`env:VAR_NAME`, `keyring:service:key`, or the literal `CHANGE_ME` — never a
real token. A startup check (`openagent.config.validate_no_literal_secrets`)
rejects the config file otherwise. See [security.md](security.md).

## 3. Sanity-check the install (fully offline)

```bash
openagent --version
openagent models list
openagent skills list
openagent security secret-scan .
pytest -q
```

None of these commands download model weights or contact a remote backend.

## 4. Bring up a remote GPU backend

Pick one (Colab first is recommended — it's simpler to get a working
end-to-end loop with a single free T4):

- **Colab**: follow [provider-limits.md](provider-limits.md#colab) and
  [mcp.md](mcp.md#colab-mcp) — generate the bootstrap with
  `openagent providers bootstrap colab <model-id> --out-dir ./bootstrap/colab`,
  open it in Colab, run the cells, and connect through `colab-mcp`.
- **Kaggle**: follow [provider-limits.md](provider-limits.md#kaggle) and
  [mcp.md](mcp.md#kaggle-mcp) — generate the bootstrap with
  `openagent providers bootstrap kaggle <model-id> --out-dir ./bootstrap/kaggle`,
  push the generated kernel, and poll it through `kaggle-mcp`.

## 5. Start a session

```bash
openagent new --workspace /path/to/your/project
openagent sessions
openagent status <session_id>
```

See [session-lifecycle.md](session-lifecycle.md) for the complete flow,
including subagents and scheduled tasks.
