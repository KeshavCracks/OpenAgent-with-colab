"""Aggregate preflight/health-check suite required before trusting a backend.

Checks, in order: GPU shape, VRAM, RAM, disk, model checksum, server health,
tool template presence, tool-call validity, latency, and quota/session state.
Any failing check blocks `gate_passed` for the model/session.
"""
from __future__ import annotations

import dataclasses

from openagent.models.registry import ModelEntry
from openagent.providers.base import GpuShape, HealthCheck, ProviderDriver, ProviderSession
from openagent.runtime.llama_cpp_runtime import HealthReport, check_server_health


@dataclasses.dataclass
class PreflightResult:
    checks: list[HealthCheck]

    @property
    def all_passed(self) -> bool:
        return all(c.ok for c in self.checks)

    def to_dict(self) -> dict:
        return {"all_passed": self.all_passed, "checks": [dataclasses.asdict(c) for c in self.checks]}


def run_preflight(
    driver: ProviderDriver,
    model: ModelEntry,
    shape: GpuShape,
    session: ProviderSession,
    server_base_url: str | None = None,
    server_token: str | None = None,
    http_get=None,
    http_post=None,
) -> PreflightResult:
    checks = list(driver.preflight_checks(model, shape))

    try:
        driver.enforce_session_limit(session)
        checks.append(HealthCheck("session_within_limit", True, f"elapsed={session.elapsed_hours():.2f}h"))
    except Exception as exc:  # noqa: BLE001
        checks.append(HealthCheck("session_within_limit", False, str(exc)))

    checks.append(HealthCheck(
        "tool_template_present",
        model.raw.get("tool_template") not in (None, ""),
        f"tool_template={model.raw.get('tool_template')}",
    ))

    if server_base_url:
        report: HealthReport = check_server_health(
            server_base_url, token=server_token, http_get=http_get, http_post=http_post,
        )
        checks.append(HealthCheck("server_reachable", report.reachable, report.detail))
        checks.append(HealthCheck("models_endpoint_ok", report.models_endpoint_ok))
        checks.append(HealthCheck("chat_completion_ok", report.chat_completion_ok))
        checks.append(HealthCheck("tool_call_valid", report.tool_call_valid))
        latency_ok = report.latency_ms is not None and report.latency_ms < 60_000
        checks.append(HealthCheck("latency_measured", latency_ok,
                                   f"latency_ms={report.latency_ms}"))
    else:
        checks.append(HealthCheck("server_reachable", False, "no server_base_url supplied"))

    return PreflightResult(checks=checks)
