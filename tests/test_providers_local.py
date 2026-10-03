import time

from openagent.config import ProviderLimits
from openagent.providers.base import ProviderSession, SessionState
from openagent.providers.local import LocalDriver
from openagent.runtime.llama_cpp_runtime import HealthReport


def _session():
    return ProviderSession(provider="local", session_id="s1", started_at=time.time())


def test_detect_gpu_reflects_configured_limits():
    limits = ProviderLimits(vram_gb=24, ram_gb=32, cpu_cores=8, disk_gb=100)
    driver = LocalDriver(limits)
    shape = driver.detect_gpu()
    assert shape.vram_gb == 24
    assert shape.ram_gb == 32
    assert shape.cpu_cores == 8


def test_generate_bootstrap_is_empty_for_user_managed_runtime():
    driver = LocalDriver(ProviderLimits())
    assert driver.generate_bootstrap(model=None, out_dir="/tmp/whatever") == []


def test_start_marks_running_and_records_model(monkeypatch):
    from openagent.models.registry import load_registry

    driver = LocalDriver(ProviderLimits())
    session = _session()
    model = load_registry().default()
    result = driver.start(model, session)
    assert result.state == SessionState.RUNNING
    assert result.model_id == model.id
    assert result.started_at is not None


def test_status_healthy_marks_session_running(monkeypatch):
    driver = LocalDriver(ProviderLimits())
    session = _session()

    def fake_check_server_health(base_url, token=None):
        return HealthReport(reachable=True, models_endpoint_ok=True, chat_completion_ok=True,
                             tool_call_valid=True, detail="ok")

    monkeypatch.setattr("openagent.providers.local.check_server_health", fake_check_server_health)
    result = driver.status(session)
    assert result.state == SessionState.RUNNING
    assert result.checks[-1].name == "server_reachable"
    assert result.checks[-1].ok is True


def test_status_unhealthy_marks_session_degraded(monkeypatch):
    driver = LocalDriver(ProviderLimits())
    session = _session()

    def fake_check_server_health(base_url, token=None):
        return HealthReport(reachable=False, detail="connection refused")

    monkeypatch.setattr("openagent.providers.local.check_server_health", fake_check_server_health)
    result = driver.status(session)
    assert result.state == SessionState.DEGRADED
    assert result.checks[-1].ok is False


def test_checkpoint_and_stop():
    driver = LocalDriver(ProviderLimits())
    session = _session()
    ckpt = driver.checkpoint(session, label="manual")
    assert ckpt["label"] == "manual"
    assert session.checkpoints == [ckpt]

    stopped = driver.stop(session)
    assert stopped.state == SessionState.STOPPED
