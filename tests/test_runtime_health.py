from openagent.models.registry import load_registry
from openagent.providers.base import GpuShape, ProviderSession
from openagent.providers.local import LocalDriver
from openagent.runtime.health import run_preflight
from openagent.runtime.llama_cpp_runtime import check_server_health
from openagent.config import ProviderLimits


def _fake_transport(models_ok=True, tool_ok=True):
    def http_get(url, headers):
        return {"data": [{"id": "default"}]} if models_ok else {}

    def http_post(url, headers, body):
        if not tool_ok:
            return {"choices": [{"message": {"content": "no tool call"}}]}
        return {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                    }],
                }
            }]
        }

    return http_get, http_post


def test_check_server_health_healthy():
    http_get, http_post = _fake_transport()
    report = check_server_health("http://127.0.0.1:8080", http_get=http_get, http_post=http_post)
    assert report.reachable
    assert report.models_endpoint_ok
    assert report.chat_completion_ok
    assert report.tool_call_valid
    assert report.healthy


def test_check_server_health_unreachable():
    def http_get(url, headers):
        raise ConnectionError("refused")

    report = check_server_health("http://127.0.0.1:8080", http_get=http_get, http_post=lambda *a: {})
    assert not report.reachable
    assert not report.healthy


def test_check_server_health_tool_call_invalid():
    http_get, http_post = _fake_transport(tool_ok=False)
    report = check_server_health("http://127.0.0.1:8080", http_get=http_get, http_post=http_post)
    assert report.reachable
    assert report.chat_completion_ok
    assert not report.tool_call_valid


def test_run_preflight_all_checks_pass():
    registry = load_registry()
    model = registry.get("qwen3.8-27b-gguf-q4km")
    shape = GpuShape(gpu_name="T4", vram_gb=15, ram_gb=12, cpu_cores=2, disk_gb=70)
    driver = LocalDriver(ProviderLimits())
    session = ProviderSession(provider="local", session_id="s1", started_at=__import__("time").time())
    http_get, http_post = _fake_transport()
    result = run_preflight(driver, model, shape, session, server_base_url="http://127.0.0.1:8080",
                            http_get=http_get, http_post=http_post)
    assert result.all_passed, result.to_dict()


def test_run_preflight_fails_on_insufficient_vram():
    registry = load_registry()
    model = registry.get("qwen3.8-27b-gguf-q4km")
    shape = GpuShape(gpu_name="T4", vram_gb=4, ram_gb=12, cpu_cores=2, disk_gb=70)
    driver = LocalDriver(ProviderLimits())
    session = ProviderSession(provider="local", session_id="s1", started_at=__import__("time").time())
    http_get, http_post = _fake_transport()
    result = run_preflight(driver, model, shape, session, server_base_url="http://127.0.0.1:8080",
                            http_get=http_get, http_post=http_post)
    assert not result.all_passed
    gpu_check = next(c for c in result.checks if c.name == "gpu_shape")
    assert gpu_check.ok is False
