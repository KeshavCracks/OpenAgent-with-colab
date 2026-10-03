"""llama.cpp runtime launcher: bootstrap script generation + health checks.

The harness never performs model inference locally -- this module only
generates the shell commands that a *remote* GPU runtime (Colab/Kaggle
container) should run, and separately provides health-check helpers the
local harness uses once an OpenAI-compatible endpoint is reachable.
"""
from __future__ import annotations

import dataclasses
import shlex
import textwrap
from typing import Any, Callable, Optional

from openagent.models.registry import ModelEntry

# Minimum llama.cpp release known (as of 2026-10-03) to register the qwen35
# architecture and MTP speculative-decoding support that Qwen3.8-27B GGUFs
# require. Pin an exact tag -- never build against a floating "latest".
PINNED_LLAMA_CPP_RELEASE = "b10896"


def generate_llama_cpp_install_script(release_tag: str = PINNED_LLAMA_CPP_RELEASE) -> str:
    """Bash: install a pinned prebuilt CUDA llama.cpp server binary.

    Falls back to building from the pinned source tag only if no matching
    prebuilt asset exists for the runtime's platform.
    """
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        LLAMA_CPP_RELEASE="{release_tag}"
        INSTALL_DIR="${{LLAMA_CPP_INSTALL_DIR:-$HOME/.openagent/llama.cpp}}"
        mkdir -p "$INSTALL_DIR"
        cd "$INSTALL_DIR"

        echo "[openagent] installing llama.cpp release ${{LLAMA_CPP_RELEASE}} (CUDA build)"
        ASSET_URL="https://github.com/ggml-org/llama.cpp/releases/download/${{LLAMA_CPP_RELEASE}}/llama-${{LLAMA_CPP_RELEASE}}-bin-ubuntu-cuda-x64.zip"
        if curl -fsSL -o llama-cuda.zip "$ASSET_URL"; then
            unzip -o -q llama-cuda.zip -d build
        else
            echo "[openagent] prebuilt asset not found, building release ${{LLAMA_CPP_RELEASE}} from source"
            if [ ! -d llama.cpp ]; then
                git clone --depth 1 --branch "${{LLAMA_CPP_RELEASE}}" https://github.com/ggml-org/llama.cpp.git
            fi
            cd llama.cpp
            cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
            cmake --build build -j"$(nproc)" --target llama-server llama-cli
            cp -r build ../build
            cd ..
        fi
        echo "[openagent] llama.cpp ready at $INSTALL_DIR/build"
    """)


def generate_model_download_script(model: ModelEntry, dest_dir: str = "$HOME/.openagent/models") -> str:
    if not model.sha256 or not model.repo or not model.filename:
        raise ValueError(f"Model {model.id} is missing repo/filename/sha256 -- cannot download safely")
    hf_token_line = (
        'if [ -z "${HF_TOKEN:-}" ]; then echo "HF_TOKEN is required for this gated model" >&2; exit 1; fi\n'
        '        AUTH_HEADER="Authorization: Bearer $HF_TOKEN"\n'
        if model.requires_authenticated_download
        else '        AUTH_HEADER=""\n'
    )
    url = f"https://huggingface.co/{model.repo}/resolve/{model.revision}/{model.filename}"
    filename = model.filename.split("/")[-1]
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        DEST_DIR="{dest_dir}"
        mkdir -p "$DEST_DIR"
        cd "$DEST_DIR"
        {hf_token_line}        EXPECTED_SHA256="{model.sha256}"
        URL="{url}"
        DEST_FILE="{filename}"

        if [ -f "$DEST_FILE" ] && echo "$EXPECTED_SHA256  $DEST_FILE" | sha256sum -c - >/dev/null 2>&1; then
            echo "[openagent] $DEST_FILE already present and checksum-verified, skipping download"
        else
            echo "[openagent] downloading {model.id} ({model.repo}@{model.revision})"
            if [ -n "${{AUTH_HEADER:-}}" ]; then
                curl -fL -H "$AUTH_HEADER" -o "$DEST_FILE.part" "$URL"
            else
                curl -fL -o "$DEST_FILE.part" "$URL"
            fi
            mv "$DEST_FILE.part" "$DEST_FILE"
            echo "$EXPECTED_SHA256  $DEST_FILE" | sha256sum -c -
            echo "[openagent] checksum verified for $DEST_FILE"
        fi
    """)


def generate_server_start_script(
    model: ModelEntry,
    bind: str = "127.0.0.1",
    port: int = 8080,
    bearer_token_env: str = "LLAMA_SERVER_TOKEN",
    model_dir: str = "$HOME/.openagent/models",
) -> str:
    flags = model.runtime_flags()
    n_ctx = flags.get("n_ctx", 8192)
    cache_k = flags.get("cache_type_k", "q8_0")
    cache_v = flags.get("cache_type_v", "q8_0")
    parallel = flags.get("parallel", 1)
    flash_attn = "--flash-attn on" if flags.get("flash_attn") else ""
    filename = (model.filename or "").split("/")[-1]
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        BIND="{bind}"
        PORT="{port}"
        MODEL_PATH="{model_dir}/{filename}"
        BEARER="${{{bearer_token_env}:-}}"
        BIN="$HOME/.openagent/llama.cpp/build/bin/llama-server"

        ARGS=(
          --model "$MODEL_PATH"
          --host "$BIND" --port "$PORT"
          --ctx-size {n_ctx}
          --cache-type-k {cache_k} --cache-type-v {cache_v}
          --parallel {parallel}
          --jinja
          --no-webui
        )
        {flash_attn}
        if [ -n "$BEARER" ]; then
          ARGS+=(--api-key "$BEARER")
        fi

        echo "[openagent] starting llama-server on ${{BIND}}:${{PORT}} (loopback by default)"
        exec "$BIN" "${{ARGS[@]}}"
    """)


def generate_full_bootstrap_script(model: ModelEntry, bind: str = "127.0.0.1", port: int = 8080) -> str:
    """One script = install + download + start, for a single Colab/Kaggle cell."""
    parts = [
        generate_llama_cpp_install_script(),
        generate_model_download_script(model),
        generate_server_start_script(model, bind=bind, port=port),
    ]
    return "\n\n# ---- next step ----\n\n".join(parts)


# ---------------------------------------------------------------------------
# Health checks (run from the LOCAL harness against a reachable endpoint, or
# from inside the remote runtime via an exec bridge -- see providers/colab.py)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class HealthReport:
    reachable: bool
    models_endpoint_ok: bool = False
    chat_completion_ok: bool = False
    tool_call_valid: bool = False
    latency_ms: float | None = None
    detail: str = ""

    @property
    def healthy(self) -> bool:
        return self.reachable and self.models_endpoint_ok and self.chat_completion_ok


HttpGet = Callable[[str, dict], Any]
HttpPost = Callable[[str, dict, dict], Any]


def check_server_health(
    base_url: str,
    token: Optional[str] = None,
    http_get: Optional[HttpGet] = None,
    http_post: Optional[HttpPost] = None,
    sample_tool_schema: Optional[dict] = None,
) -> HealthReport:
    """Validate an OpenAI-compatible llama-server endpoint.

    `http_get`/`http_post` are injectable so this can be unit-tested without
    a real network call, and so the Colab exec-bridge can route the actual
    HTTP request through in-runtime code instead of a public network path.
    """
    import time

    if http_get is None or http_post is None:
        import requests

        headers = {"Authorization": f"Bearer {token}"} if token else {}

        def _get(url, hdrs):
            r = requests.get(url, headers={**headers, **hdrs}, timeout=10)
            r.raise_for_status()
            return r.json()

        def _post(url, hdrs, json_body):
            r = requests.post(url, headers={**headers, **hdrs}, json=json_body, timeout=30)
            r.raise_for_status()
            return r.json()

        http_get = http_get or _get
        http_post = http_post or _post

    try:
        start = time.time()
        models = http_get(f"{base_url}/v1/models", {})
        models_ok = bool(models.get("data")) if isinstance(models, dict) else False
    except Exception as exc:  # noqa: BLE001
        return HealthReport(reachable=False, detail=f"GET /v1/models failed: {exc}")

    tool_schema = sample_tool_schema or {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
    try:
        resp = http_post(
            f"{base_url}/v1/chat/completions",
            {},
            {
                "model": "default",
                "messages": [{"role": "user", "content": "What is the weather in Paris? Use the tool."}],
                "tools": [tool_schema],
                "max_tokens": 64,
            },
        )
        latency_ms = (time.time() - start) * 1000
        chat_ok = bool(resp.get("choices"))
        tool_calls = []
        if chat_ok:
            tool_calls = resp["choices"][0].get("message", {}).get("tool_calls") or []
        tool_valid = any(
            tc.get("function", {}).get("name") == "get_weather"
            and "city" in (tc.get("function", {}).get("arguments") or "")
            for tc in tool_calls
        )
        return HealthReport(
            reachable=True,
            models_endpoint_ok=models_ok,
            chat_completion_ok=chat_ok,
            tool_call_valid=tool_valid,
            latency_ms=latency_ms,
            detail="ok" if chat_ok else "chat completion returned no choices",
        )
    except Exception as exc:  # noqa: BLE001
        return HealthReport(reachable=True, models_endpoint_ok=models_ok, detail=f"POST /v1/chat/completions failed: {exc}")
