"""Kaggle provider driver.

Execution model (per github.com/Galaxy-Dawn/kaggle-mcp, a local stdio MCP
server wrapping the Kaggle Kernels REST API -- distinct from colab-mcp's
live browser bridge): there is **no interactive two-way code-exec channel**
into a running kernel. The harness instead:

  1. Pushes a complete, self-contained kernel script (install + download +
     verify + start llama-server + run an in-kernel health check + write a
     JSON report to the kernel's output files) via the kernel-push tool.
  2. Polls kernel status via the status tool until it is running/complete.
  3. Reads results back through the kernel's *output* (logs / output files),
     never a live network call to the kernel, since Kaggle provides "no
     stable inbound public address" for a running kernel.

This is why Kaggle sessions in this harness are modeled as a batch job with
a result artifact, while Colab sessions are modeled as a live bridge.
"""
from __future__ import annotations

import dataclasses
import json
import os
import time
import uuid
from pathlib import Path
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
from openagent.runtime.llama_cpp_runtime import generate_full_bootstrap_script


@dataclasses.dataclass
class KaggleKernelHandle:
    kernel_ref: str  # e.g. "username/openagent-bootstrap-<model_id>"


@dataclasses.dataclass
class KaggleStatusResult:
    status: str   # queued | running | complete | error | cancelAcknowledged
    detail: str = ""


@dataclasses.dataclass
class KaggleOutputResult:
    ok: bool
    log_text: str = ""
    files: dict[str, str] = dataclasses.field(default_factory=dict)  # filename -> local path


class KaggleExecClient:
    """Shape of the kaggle-mcp tool surface this driver depends on."""

    def push_kernel(self, kernel_dir: str) -> KaggleKernelHandle:  # pragma: no cover
        raise NotImplementedError

    def get_status(self, handle: KaggleKernelHandle) -> KaggleStatusResult:  # pragma: no cover
        raise NotImplementedError

    def get_output(self, handle: KaggleKernelHandle) -> KaggleOutputResult:  # pragma: no cover
        raise NotImplementedError

    def cancel(self, handle: KaggleKernelHandle) -> bool:  # pragma: no cover
        raise NotImplementedError


KAGGLE_GPU_OPTIONS = {"t4x2": {"gpu_name": "T4 x2", "vram_gb": 30.0}}


def generate_kernel_metadata(model: ModelEntry, username_placeholder: str = "YOUR_KAGGLE_USERNAME") -> dict:
    return {
        "id": f"{username_placeholder}/openagent-bootstrap-{model.id}".lower().replace(".", "-"),
        "title": f"openagent-bootstrap-{model.id}",
        "code_file": "kernel.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
    }


def generate_kernel_script(model: ModelEntry, bind: str = "127.0.0.1", port: int = 8080) -> str:
    bootstrap = generate_full_bootstrap_script(model, bind=bind, port=port)
    # Kaggle kernels run to completion and are read back via logs/output
    # files, so we background the server, run checks, and dump a JSON
    # report + always terminate cleanly well within the 12h session cap.
    return f'''"""OpenAgent Harness -- Kaggle bootstrap kernel for {model.id}.

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

BOOTSTRAP_SCRIPT = r"""{bootstrap}"""

report = {{"model_id": "{model.id}", "started_at": time.time()}}

with open("bootstrap.sh", "w") as f:
    f.write(BOOTSTRAP_SCRIPT)
os.chmod("bootstrap.sh", 0o755)

proc = subprocess.Popen(["bash", "bootstrap.sh"])
# Give the server time to come up before health-checking; this kernel keeps
# running (well under the ~12h session cap) so later cells / a supervising
# loop can keep polling if needed.
time.sleep(30)

try:
    with urllib.request.urlopen("http://{bind}:{port}/v1/models", timeout=10) as resp:
        report["models_endpoint_ok"] = resp.status == 200
        report["models_response"] = resp.read().decode()[:2000]
except Exception as exc:  # noqa: BLE001
    report["models_endpoint_ok"] = False
    report["error"] = str(exc)

report["finished_at"] = time.time()
with open("/kaggle/working/openagent_report.json", "w") as f:
    json.dump(report, f, indent=2)
print(json.dumps(report, indent=2))
'''


class KaggleDriver(ProviderDriver):
    name = "kaggle"

    def __init__(self, limits: ProviderLimits, exec_client: Optional[KaggleExecClient] = None):
        super().__init__(limits)
        self.exec_client = exec_client
        self._handles: dict[str, KaggleKernelHandle] = {}

    def detect_gpu(self) -> GpuShape:
        # Kaggle doesn't expose a pre-session GPU query through kaggle-mcp;
        # the accelerator is selected via kernel metadata (enable_gpu +
        # kernel settings UI/API), so we report the configured limits.
        return GpuShape(
            gpu_name="T4x2", vram_gb=self.limits.vram_gb, ram_gb=self.limits.ram_gb,
            cpu_cores=self.limits.cpu_cores, disk_gb=self.limits.disk_gb,
        )

    def generate_bootstrap(self, model: ModelEntry, out_dir: str) -> list[str]:
        os.makedirs(out_dir, exist_ok=True)
        meta_path = Path(out_dir) / "kernel-metadata.json"
        script_path = Path(out_dir) / "kernel.py"
        meta_path.write_text(json.dumps(generate_kernel_metadata(model), indent=2), encoding="utf-8")
        script_path.write_text(generate_kernel_script(model), encoding="utf-8")
        return [str(meta_path), str(script_path)]

    def start(self, model: ModelEntry, session: ProviderSession) -> ProviderSession:
        if not self.exec_client:
            raise ProviderError(
                "Kaggle start() requires an exec_client implementing the kaggle-mcp "
                "kernel push/status/output tool surface."
            )
        import tempfile

        session.state = SessionState.BOOTSTRAPPING
        with tempfile.TemporaryDirectory() as tmp:
            self.generate_bootstrap(model, tmp)
            handle = self.exec_client.push_kernel(tmp)
        self._handles[session.session_id] = handle
        session.state = SessionState.RUNNING
        session.started_at = time.time()
        session.model_id = model.id
        return session

    def status(self, session: ProviderSession) -> ProviderSession:
        handle = self._handles.get(session.session_id)
        if not handle or not self.exec_client:
            return session
        result = self.exec_client.get_status(handle)
        ok = result.status in ("running", "complete")
        session.checks.append(HealthCheck("kernel_status", ok, result.status))
        session.state = SessionState.RUNNING if result.status == "running" else (
            SessionState.STOPPED if result.status == "complete" else
            SessionState.FAILED if result.status == "error" else session.state
        )
        try:
            self.enforce_session_limit(session)
        except Exception:
            session.state = SessionState.EXPIRED
        return session

    def checkpoint(self, session: ProviderSession, label: str) -> dict:
        handle = self._handles.get(session.session_id)
        ckpt = {"id": str(uuid.uuid4())[:8], "label": label, "t": time.time(), "session_id": session.session_id}
        if handle and self.exec_client:
            output = self.exec_client.get_output(handle)
            ckpt["kernel_log_excerpt"] = output.log_text[-2000:]
            ckpt["files"] = list(output.files.keys())
        session.checkpoints.append(ckpt)
        return ckpt

    def stop(self, session: ProviderSession) -> ProviderSession:
        handle = self._handles.get(session.session_id)
        if handle and self.exec_client:
            self.exec_client.cancel(handle)
        session.state = SessionState.STOPPED
        return session
