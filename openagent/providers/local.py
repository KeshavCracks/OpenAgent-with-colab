"""Local / "bring your own endpoint" provider.

Used when the user already has an OpenAI-compatible llama-server reachable
(their own GPU box, a tunnel they manage themselves, etc). No bootstrap is
generated; this driver only performs health checks and session bookkeeping
against a URL the user supplies.
"""
from __future__ import annotations

import time

from openagent.config import ProviderLimits
from openagent.models.registry import ModelEntry
from openagent.providers.base import GpuShape, HealthCheck, ProviderDriver, ProviderSession, SessionState
from openagent.runtime.llama_cpp_runtime import check_server_health


class LocalDriver(ProviderDriver):
    name = "local"

    def __init__(self, limits: ProviderLimits, base_url: str = "http://127.0.0.1:8080", token: str | None = None):
        super().__init__(limits)
        self.base_url = base_url
        self.token = token

    def detect_gpu(self) -> GpuShape:
        return GpuShape(gpu_name="unknown-local", vram_gb=self.limits.vram_gb,
                         ram_gb=self.limits.ram_gb, cpu_cores=self.limits.cpu_cores,
                         disk_gb=self.limits.disk_gb)

    def generate_bootstrap(self, model: ModelEntry, out_dir: str) -> list[str]:
        return []  # user manages their own runtime

    def start(self, model: ModelEntry, session: ProviderSession) -> ProviderSession:
        session.state = SessionState.RUNNING
        session.started_at = time.time()
        session.model_id = model.id
        return session

    def status(self, session: ProviderSession) -> ProviderSession:
        report = check_server_health(self.base_url, token=self.token)
        session.checks.append(HealthCheck("server_reachable", report.reachable, report.detail))
        session.state = SessionState.RUNNING if report.healthy else SessionState.DEGRADED
        return session

    def checkpoint(self, session: ProviderSession, label: str) -> dict:
        ckpt = {"label": label, "t": time.time()}
        session.checkpoints.append(ckpt)
        return ckpt

    def stop(self, session: ProviderSession) -> ProviderSession:
        session.state = SessionState.STOPPED
        return session
