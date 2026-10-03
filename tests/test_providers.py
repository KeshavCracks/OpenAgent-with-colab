import time
from pathlib import Path

import pytest

from openagent.config import ProviderLimits
from openagent.models.registry import load_registry
from openagent.providers.base import GpuShape, ProviderSession, QuotaExceededError, SessionState
from openagent.providers.colab import ColabDriver, ColabExecResult, generate_colab_notebook
from openagent.providers.kaggle import (
    KaggleDriver,
    KaggleExecClient,
    KaggleKernelHandle,
    KaggleOutputResult,
    KaggleStatusResult,
    generate_kernel_metadata,
    generate_kernel_script,
)


@pytest.fixture
def model():
    return load_registry().get("qwen3.8-27b-gguf-q4km")


# --------------------------------------------------------------------- Colab
class FakeColabExecClient:
    def __init__(self):
        self.calls = []

    def __call__(self, code: str) -> ColabExecResult:
        self.calls.append(code)
        if "nvidia-smi" in code:
            return ColabExecResult(ok=True, stdout="Tesla T4, 15360 MiB\n")
        if "v1/models" in code:
            return ColabExecResult(ok=True, stdout='{"data": [{"id": "default"}]}')
        return ColabExecResult(ok=True, stdout="ok")


def test_colab_bootstrap_generates_notebook_and_script(tmp_path, model):
    driver = ColabDriver(ProviderLimits())
    files = driver.generate_bootstrap(model, str(tmp_path))
    assert len(files) == 2
    for f in files:
        assert Path(f).exists()
    notebook = generate_colab_notebook(model)
    assert notebook["metadata"]["accelerator"] == "GPU"


def test_colab_detect_gpu_uses_exec_bridge(model):
    client = FakeColabExecClient()
    driver = ColabDriver(ProviderLimits(), exec_client=client)
    shape = driver.detect_gpu()
    assert isinstance(shape, GpuShape)
    assert shape.gpu_name == "Tesla T4"
    assert shape.vram_gb == pytest.approx(15.0, abs=0.1)


def test_colab_detect_gpu_without_bridge_raises():
    driver = ColabDriver(ProviderLimits())
    with pytest.raises(Exception):
        driver.detect_gpu()


def test_colab_start_status_stop_lifecycle(model):
    client = FakeColabExecClient()
    driver = ColabDriver(ProviderLimits(), exec_client=client)
    session = ProviderSession(provider="colab", session_id="s1")
    session = driver.start(model, session)
    assert session.state == SessionState.RUNNING
    session = driver.status(session)
    assert session.state == SessionState.RUNNING
    ckpt = driver.checkpoint(session, "after-setup")
    assert ckpt["label"] == "after-setup"
    session = driver.stop(session)
    assert session.state == SessionState.STOPPED


def test_colab_session_limit_enforced(model):
    client = FakeColabExecClient()
    limits = ProviderLimits(max_session_hours=0.0000001)
    driver = ColabDriver(limits, exec_client=client)
    session = ProviderSession(provider="colab", session_id="s1", started_at=time.time() - 10)
    with pytest.raises(QuotaExceededError):
        driver.enforce_session_limit(session)


# -------------------------------------------------------------------- Kaggle
class FakeKaggleExecClient(KaggleExecClient):
    def __init__(self):
        self.pushed_dirs = []
        self._status = "running"

    def push_kernel(self, kernel_dir: str) -> KaggleKernelHandle:
        self.pushed_dirs.append(kernel_dir)
        assert (Path(kernel_dir) / "kernel-metadata.json").exists()
        assert (Path(kernel_dir) / "kernel.py").exists()
        return KaggleKernelHandle(kernel_ref="user/openagent-bootstrap-fake")

    def get_status(self, handle: KaggleKernelHandle) -> KaggleStatusResult:
        return KaggleStatusResult(status=self._status)

    def get_output(self, handle: KaggleKernelHandle) -> KaggleOutputResult:
        return KaggleOutputResult(ok=True, log_text="models_endpoint_ok: true", files={"openagent_report.json": "/tmp/x"})

    def cancel(self, handle: KaggleKernelHandle) -> bool:
        return True


def test_kaggle_bootstrap_generates_kernel_files(tmp_path, model):
    driver = KaggleDriver(ProviderLimits())
    files = driver.generate_bootstrap(model, str(tmp_path))
    assert len(files) == 2
    meta = generate_kernel_metadata(model)
    assert meta["enable_gpu"] is True
    script = generate_kernel_script(model)
    assert "openagent_report.json" in script


def test_kaggle_start_status_checkpoint_stop(model):
    client = FakeKaggleExecClient()
    driver = KaggleDriver(ProviderLimits(), exec_client=client)
    session = ProviderSession(provider="kaggle", session_id="k1")
    session = driver.start(model, session)
    assert session.state == SessionState.RUNNING
    assert client.pushed_dirs

    session = driver.status(session)
    assert session.state == SessionState.RUNNING

    ckpt = driver.checkpoint(session, "mid-run")
    assert "openagent_report.json" in ckpt["files"]

    session = driver.stop(session)
    assert session.state == SessionState.STOPPED


def test_kaggle_status_complete_marks_session_stopped(model):
    client = FakeKaggleExecClient()
    client._status = "complete"
    driver = KaggleDriver(ProviderLimits(), exec_client=client)
    session = ProviderSession(provider="kaggle", session_id="k2")
    session = driver.start(model, session)
    session = driver.status(session)
    assert session.state == SessionState.STOPPED


def test_kaggle_requires_exec_client_to_start(model):
    driver = KaggleDriver(ProviderLimits())
    session = ProviderSession(provider="kaggle", session_id="k3")
    with pytest.raises(Exception):
        driver.start(model, session)
