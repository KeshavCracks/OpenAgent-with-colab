"""OpenAgent Harness -- Kaggle bootstrap kernel for qwen3.8-27b-gguf-q4km.

Batch-style: this script installs llama.cpp, downloads + checksum-verifies
the pinned model, starts llama-server on loopback, runs an in-kernel health
check, and writes a JSON report to /kaggle/working/openagent_report.json.
Results are read back via kaggle-mcp's kernel-output tool, not a live
network call (Kaggle provides no stable inbound public address).
"""
import json
import os
import subprocess
import time
import urllib.request

BOOTSTRAP_SCRIPT = r"""#!/usr/bin/env bash
set -euo pipefail
LLAMA_CPP_RELEASE="b10896"
INSTALL_DIR="${LLAMA_CPP_INSTALL_DIR:-$HOME/.openagent/llama.cpp}"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo "[openagent] installing llama.cpp release ${LLAMA_CPP_RELEASE} (CUDA build)"
ASSET_URL="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_CPP_RELEASE}/llama-${LLAMA_CPP_RELEASE}-bin-ubuntu-cuda-x64.zip"
if curl -fsSL -o llama-cuda.zip "$ASSET_URL"; then
    unzip -o -q llama-cuda.zip -d build
else
    echo "[openagent] prebuilt asset not found, building release ${LLAMA_CPP_RELEASE} from source"
    if [ ! -d llama.cpp ]; then
        git clone --depth 1 --branch "${LLAMA_CPP_RELEASE}" https://github.com/ggml-org/llama.cpp.git
    fi
    cd llama.cpp
    cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
    cmake --build build -j"$(nproc)" --target llama-server llama-cli
    cp -r build ../build
    cd ..
fi
echo "[openagent] llama.cpp ready at $INSTALL_DIR/build"


# ---- next step ----

#!/usr/bin/env bash
set -euo pipefail
DEST_DIR="$HOME/.openagent/models"
mkdir -p "$DEST_DIR"
cd "$DEST_DIR"
        AUTH_HEADER=""
EXPECTED_SHA256="322e194ff79741c7baa497c240f677f54b201b0efab44ca8e50f122b39123482"
URL="https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/4ca720788d1e01f1bff70c033e0d0028fd02e502/Qwen3.8-27B-UD-Q4_K_M.gguf"
DEST_FILE="Qwen3.8-27B-UD-Q4_K_M.gguf"

if [ -f "$DEST_FILE" ] && echo "$EXPECTED_SHA256  $DEST_FILE" | sha256sum -c - >/dev/null 2>&1; then
    echo "[openagent] $DEST_FILE already present and checksum-verified, skipping download"
else
    echo "[openagent] downloading qwen3.8-27b-gguf-q4km (unsloth/Qwen3.8-27B-GGUF@4ca720788d1e01f1bff70c033e0d0028fd02e502)"
    if [ -n "${AUTH_HEADER:-}" ]; then
        curl -fL -H "$AUTH_HEADER" -o "$DEST_FILE.part" "$URL"
    else
        curl -fL -o "$DEST_FILE.part" "$URL"
    fi
    mv "$DEST_FILE.part" "$DEST_FILE"
    echo "$EXPECTED_SHA256  $DEST_FILE" | sha256sum -c -
    echo "[openagent] checksum verified for $DEST_FILE"
fi


# ---- next step ----

#!/usr/bin/env bash
set -euo pipefail
BIND="127.0.0.1"
PORT="8080"
MODEL_PATH="$HOME/.openagent/models/Qwen3.8-27B-UD-Q4_K_M.gguf"
BEARER="${LLAMA_SERVER_TOKEN:-}"
BIN="$HOME/.openagent/llama.cpp/build/bin/llama-server"

ARGS=(
  --model "$MODEL_PATH"
  --host "$BIND" --port "$PORT"
  --ctx-size 8192
  --cache-type-k q8_0 --cache-type-v q8_0
  --parallel 1
  --jinja
  --no-webui
)
--flash-attn on
if [ -n "$BEARER" ]; then
  ARGS+=(--api-key "$BEARER")
fi

echo "[openagent] starting llama-server on ${BIND}:${PORT} (loopback by default)"
exec "$BIN" "${ARGS[@]}"
"""

report = {"model_id": "qwen3.8-27b-gguf-q4km", "started_at": time.time()}

with open("bootstrap.sh", "w") as f:
    f.write(BOOTSTRAP_SCRIPT)
os.chmod("bootstrap.sh", 0o755)

proc = subprocess.Popen(["bash", "bootstrap.sh"])
# Give the server time to come up before health-checking; this kernel keeps
# running (well under the ~12h session cap) so later cells / a supervising
# loop can keep polling if needed.
time.sleep(30)

try:
    with urllib.request.urlopen("http://127.0.0.1:8080/v1/models", timeout=10) as resp:
        report["models_endpoint_ok"] = resp.status == 200
        report["models_response"] = resp.read().decode()[:2000]
except Exception as exc:  # noqa: BLE001
    report["models_endpoint_ok"] = False
    report["error"] = str(exc)

report["finished_at"] = time.time()
with open("/kaggle/working/openagent_report.json", "w") as f:
    json.dump(report, f, indent=2)
print(json.dumps(report, indent=2))
