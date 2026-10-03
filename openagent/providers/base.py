"""Provider driver base class: Colab/Kaggle GPU backends.

Both providers are implemented against the *same* lifecycle contract
(start/status/checkpoint/stop) even though their underlying execution model
is different:

  * Colab (googlecolab/colab-mcp): bridges to a Colab notebook that is
    already open in the user's browser, through a local MCP client that
    supports `notifications/tools/list_changed`. There is no independent
    network path to the runtime -- all orchestration happens by asking the
    bridge to execute code *inside* that already-open notebook, and reading
    results back over the same channel. See openagent/providers/colab.py.

  * Kaggle (Galaxy-Dawn/kaggle-mcp, a local stdio wrapper around the Kaggle
    Kernels REST API): there is no live two-way code-exec channel into a
    running kernel. Instead, the harness pushes a complete kernel script,
    starts it, and polls status/output -- a batch model, not an interactive
    one. See openagent/providers/kaggle.py.

Neither driver ever exposes an unauthenticated public inference endpoint;
all HTTP calls to the in-runtime llama-server stay on loopback and are
reached through the provider's own execution channel (exec bridge or kernel
output), never a public tunnel, unless the user explicitly opts into a
short-lived authenticated tunnel for an advanced workflow.
"""
from __future__ import annotations

import dataclasses
import time
from enum import Enum
from typing import Any, Optional

from openagent.config import ProviderLimits
from openagent.models.registry import ModelEntry


class SessionState(str, Enum):
    NOT_STARTED = "not_started"
    BOOTSTRAPPING = "bootstrapping"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclasses.dataclass
class GpuShape:
    gpu_name: str
    vram_gb: float
    ram_gb: float
    cpu_cores: int
    disk_gb: float


@dataclasses.dataclass
class HealthCheck:
    name: str
    ok: bool
    detail: str = ""


@dataclasses.dataclass
class ProviderSession:
    provider: str
    session_id: str
    state: SessionState = SessionState.NOT_STARTED
    started_at: float | None = None
    model_id: str | None = None
    checks: list[HealthCheck] = dataclasses.field(default_factory=list)
    checkpoints: list[dict] = dataclasses.field(default_factory=list)

    def elapsed_hours(self) -> float:
        if not self.started_at:
            return 0.0
        return (time.time() - self.started_at) / 3600.0

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["state"] = self.state.value
        d["elapsed_hours"] = round(self.elapsed_hours(), 3)
        return d


class ProviderError(RuntimeError):
    pass


class QuotaExceededError(ProviderError):
    pass


class ProviderDriver:
    """Common contract implemented by ColabDriver and KaggleDriver."""

    name: str = "base"

    def __init__(self, limits: ProviderLimits):
        self.limits = limits

    # -- required lifecycle surface -------------------------------------
    def detect_gpu(self) -> GpuShape:  # pragma: no cover - overridden
        raise NotImplementedError

    def generate_bootstrap(self, model: ModelEntry, out_dir: str) -> list[str]:
        raise NotImplementedError

    def start(self, model: ModelEntry, session: ProviderSession) -> ProviderSession:
        raise NotImplementedError

    def status(self, session: ProviderSession) -> ProviderSession:
        raise NotImplementedError

    def checkpoint(self, session: ProviderSession, label: str) -> dict:
        raise NotImplementedError

    def stop(self, session: ProviderSession) -> ProviderSession:
        raise NotImplementedError

    # -- shared quota/session guardrails ---------------------------------
    def enforce_session_limit(self, session: ProviderSession) -> None:
        if session.elapsed_hours() > self.limits.max_session_hours:
            raise QuotaExceededError(
                f"{self.name}: session exceeded provider max_session_hours="
                f"{self.limits.max_session_hours}; stop and checkpoint now."
            )

    def preflight_checks(self, model: ModelEntry, shape: GpuShape) -> list[HealthCheck]:
        checks = []
        checks.append(HealthCheck(
            "gpu_shape", shape.vram_gb >= (model.raw.get("hardware", {}).get("min_vram_gb") or 0),
            f"vram={shape.vram_gb}GB model.min_vram_gb={model.raw.get('hardware', {}).get('min_vram_gb')}",
        ))
        checks.append(HealthCheck(
            "ram", shape.ram_gb >= (model.raw.get("hardware", {}).get("min_ram_gb") or 0),
            f"ram={shape.ram_gb}GB model.min_ram_gb={model.raw.get('hardware', {}).get('min_ram_gb')}",
        ))
        checks.append(HealthCheck(
            "disk", shape.disk_gb >= (model.size_bytes or 0) / 1e9 + 2,
            f"disk={shape.disk_gb}GB needed={(model.size_bytes or 0)/1e9:.1f}GB+headroom",
        ))
        checks.append(HealthCheck("model_checksum_pinned", bool(model.sha256), "sha256 present in registry"))
        return checks
