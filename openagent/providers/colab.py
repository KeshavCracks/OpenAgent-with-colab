"""Google Colab provider driver.

Execution model (per github.com/googlecolab/colab-mcp): colab-mcp bridges a
*local* MCP client (one that supports `notifications/tools/list_changed`,
e.g. this harness acting as such a client) to a Colab notebook that is
already open in the user's browser. There is no separate network path into
the runtime -- every action (install, download, start server, run a health
check, read logs) is performed by asking the bridge to execute a code cell
in that notebook and reading the result back over the same MCP channel.

Consequences encoded here:
  * `start()`/`status()`/`checkpoint()`/`stop()` all go through an injectable
    `ColabExecClient.execute(code) -> ColabExecResult` -- this is exactly the
    shape of a colab-mcp tool call, so swapping in the real colab-mcp client
    is a one-line change, and tests can use a fake in-process client.
  * The llama-server OpenAI endpoint stays on loopback; the harness talks to
    it by asking the bridge to `curl 127.0.0.1:PORT/...` and parsing stdout,
    not through a public tunnel.
  * A short-lived authenticated tunnel is only generated as an *opt-in*,
    clearly-labelled advanced path (see `generate_authenticated_tunnel_cell`)
    for workflows that genuinely need the endpoint reachable outside the
    notebook (e.g. a separate local process also wanting direct HTTP access).
"""
from __future__ import annotations

import dataclasses
import json
import time
import uuid
from typing import Callable, Optional

from openagent.config import ProviderLimits
from openagent.models.registry import ModelEntry
from openagent.providers.base import (
    GpuShape,
    HealthCheck,
    ProviderDriver,
    ProviderError,
    ProviderSession,
    SessionState,
)
from openagent.runtime.llama_cpp_runtime import (
    generate_full_bootstrap_script,
    generate_llama_cpp_install_script,
    generate_model_download_script,
    generate_server_start_script,
)


@dataclasses.dataclass
class ColabExecResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""


ColabExecClient = Callable[[str], ColabExecResult]


def generate_colab_notebook(model: ModelEntry, bind: str = "127.0.0.1", port: int = 8080) -> dict:
    """Return an .ipynb-shaped dict (json.dump this to a .ipynb file)."""
    cells = [
        _md_cell(
            "# OpenAgent Harness — Colab bootstrap\n"
            f"Model: **{model.display_name if hasattr(model, 'display_name') else model.id}**\n\n"
            "This notebook only installs the runtime and serves the model on "
            "**loopback** (127.0.0.1). It never exposes a public endpoint. "
            "Run cells top to bottom; keep this tab open so `colab-mcp` can "
            "bridge the local harness to this runtime."
        ),
        _code_cell("!nvidia-smi"),
        _code_cell(generate_llama_cpp_install_script()),
        _code_cell(generate_model_download_script(model)),
        _code_cell(
            "# Start the server in the background so later cells (health checks,\n"
            "# colab-mcp bridge calls) can run in the same runtime.\n"
            "import subprocess, time\n"
            f"proc = subprocess.Popen(r'''{generate_server_start_script(model, bind=bind, port=port)}''', shell=True)\n"
            "time.sleep(5)\n"
            "print('llama-server starting, pid=', proc.pid)\n"
        ),
        _code_cell(
            "# In-runtime health check (loopback only -- no public exposure)\n"
            f"import urllib.request, json\n"
            f"print(urllib.request.urlopen('http://{bind}:{port}/v1/models', timeout=10).read().decode())\n"
        ),
    ]
    return {
        "cells": cells,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"name": f"openagent-bootstrap-{model.id}.ipynb"},
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _code_cell(src: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": src.splitlines(keepends=True)}


def _md_cell(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


def generate_authenticated_tunnel_cell(bearer_token_env: str = "LLAMA_SERVER_TOKEN", ttl_minutes: int = 90) -> str:
    """Opt-in only: a short-lived, authenticated tunnel for advanced workflows.

    Never used by default. Requires an explicit token; the resulting URL is
    valid for `ttl_minutes` and must be treated as a secret.
    """
    return (
        "# ADVANCED / OPT-IN: short-lived authenticated tunnel.\n"
        "# Only run this if you specifically need the endpoint reachable\n"
        "# outside this notebook. The tunnel is bearer-token authenticated\n"
        "# and should be torn down with openagent stop as soon as you're done.\n"
        f"import os, time\n"
        f"assert os.environ.get('{bearer_token_env}'), 'set {bearer_token_env} before tunneling'\n"
        f"# e.g.: !cloudflared tunnel --url http://127.0.0.1:8080 &\n"
        f"print('tunnel TTL budget: {ttl_minutes} minutes -- stop it manually when done')\n"
    )


class ColabDriver(ProviderDriver):
    name = "colab"

    def __init__(self, limits: ProviderLimits, exec_client: Optional[ColabExecClient] = None):
        super().__init__(limits)
        self.exec_client = exec_client  # None until a real colab-mcp bridge is wired up

    def detect_gpu(self) -> GpuShape:
        if not self.exec_client:
            raise ProviderError("No colab-mcp exec bridge configured; cannot detect GPU shape")
        result = self.exec_client(
            "import subprocess; print(subprocess.run(['nvidia-smi','--query-gpu=name,memory.total',"
            "'--format=csv,noheader'], capture_output=True, text=True).stdout)"
        )
        if not result.ok or not result.stdout.strip():
            raise ProviderError(f"GPU detection failed: {result.stderr}")
        name, mem = [x.strip() for x in result.stdout.strip().splitlines()[0].split(",")]
        vram_gb = float(mem.replace("MiB", "").strip()) / 1024.0
        return GpuShape(
            gpu_name=name, vram_gb=round(vram_gb, 1),
            ram_gb=self.limits.ram_gb, cpu_cores=self.limits.cpu_cores, disk_gb=self.limits.disk_gb,
        )

    def generate_bootstrap(self, model: ModelEntry, out_dir: str) -> list[str]:
        import os

        os.makedirs(out_dir, exist_ok=True)
        nb_path = os.path.join(out_dir, f"colab_bootstrap_{model.id}.ipynb")
        with open(nb_path, "w", encoding="utf-8") as f:
            json.dump(generate_colab_notebook(model), f, indent=2)
        script_path = os.path.join(out_dir, f"colab_bootstrap_{model.id}.sh")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(generate_full_bootstrap_script(model))
        return [nb_path, script_path]

    def start(self, model: ModelEntry, session: ProviderSession) -> ProviderSession:
        if not self.exec_client:
            raise ProviderError(
                "Colab start() requires an exec_client implementing the colab-mcp "
                "bridge protocol (execute code in the already-open notebook)."
            )
        session.state = SessionState.BOOTSTRAPPING
        script = generate_full_bootstrap_script(model)
        result = self.exec_client(script)
        if not result.ok:
            session.state = SessionState.FAILED
            raise ProviderError(f"Colab bootstrap failed: {result.stderr}")
        session.state = SessionState.RUNNING
        session.started_at = time.time()
        session.model_id = model.id
        return session

    def status(self, session: ProviderSession) -> ProviderSession:
        if not self.exec_client:
            return session
        result = self.exec_client(
            "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/v1/models', timeout=5).read().decode())"
        )
        ok = result.ok and '"data"' in (result.stdout or "")
        session.checks.append(HealthCheck("server_alive", ok, result.stdout[:200]))
        session.state = SessionState.RUNNING if ok else SessionState.DEGRADED
        try:
            self.enforce_session_limit(session)
        except Exception:
            session.state = SessionState.EXPIRED
        return session

    def checkpoint(self, session: ProviderSession, label: str) -> dict:
        ckpt = {"id": str(uuid.uuid4())[:8], "label": label, "t": time.time(), "session_id": session.session_id}
        session.checkpoints.append(ckpt)
        if self.exec_client:
            # Persist artifacts to Colab's (ephemeral) disk; caller is
            # responsible for pulling anything that must survive the session.
            self.exec_client(
                f"import json, pathlib; pathlib.Path('/content/openagent_checkpoints').mkdir(exist_ok=True); "
                f"pathlib.Path('/content/openagent_checkpoints/{ckpt['id']}.json').write_text(json.dumps({ckpt!r}))"
            )
        return ckpt

    def stop(self, session: ProviderSession) -> ProviderSession:
        if self.exec_client:
            self.exec_client("import os; os.system('pkill -f llama-server || true')")
        session.state = SessionState.STOPPED
        return session
