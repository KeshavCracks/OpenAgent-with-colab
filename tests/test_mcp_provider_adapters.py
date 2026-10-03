import pytest

from openagent.mcp.manager import MCPError
from openagent.mcp.servers.colab_mcp import ColabMcpExecClient, default_colab_mcp_spec
from openagent.mcp.servers.kaggle_mcp import KaggleMcpExecClient, default_kaggle_mcp_spec
from openagent.providers.kaggle import KaggleKernelHandle


class FakeStdioClient:
    def __init__(self, tools, call_results=None, raise_on_call=None):
        self._tools = tools
        self.started = False
        self.stopped = False
        self.calls = []
        self._call_results = call_results or {}
        self._raise_on_call = raise_on_call

    def start(self, timeout=10.0):
        self.started = True

    def stop(self):
        self.stopped = True

    def list_tools(self):
        return [{"name": t} for t in self._tools]

    def call_tool(self, name, arguments, timeout=30):
        self.calls.append((name, arguments))
        if self._raise_on_call and name == self._raise_on_call:
            raise MCPError(f"{name} failed")
        return self._call_results.get(name, {})


def test_default_colab_mcp_spec_not_public_and_pinned_command():
    spec = default_colab_mcp_spec()
    assert spec.public_endpoint is False
    assert spec.command[0] == "uvx"
    assert "colab-mcp" in spec.command[-1]


def test_colab_mcp_discovers_exec_tool_and_executes():
    fake = FakeStdioClient(tools=["execute_cell"],
                            call_results={"execute_cell": {"stdout": "hello", "stderr": ""}})
    client = ColabMcpExecClient(client=fake)
    result = client("print('hi')")
    assert fake.started
    assert result.ok
    assert result.stdout == "hello"
    assert fake.calls[0][0] == "execute_cell"


def test_colab_mcp_raises_clear_error_when_no_exec_tool_found():
    fake = FakeStdioClient(tools=["some_other_tool"])
    client = ColabMcpExecClient(client=fake)
    with pytest.raises(MCPError):
        client("print('hi')")


def test_colab_mcp_wraps_tool_failure_as_failed_exec_result():
    fake = FakeStdioClient(tools=["run_cell"], raise_on_call="run_cell")
    client = ColabMcpExecClient(client=fake)
    result = client("boom")
    assert result.ok is False
    assert "failed" in result.stderr


def test_colab_mcp_close_stops_client():
    fake = FakeStdioClient(tools=["execute_cell"], call_results={"execute_cell": {"stdout": "x"}})
    client = ColabMcpExecClient(client=fake)
    client("noop")
    client.close()
    assert fake.stopped


def test_default_kaggle_mcp_spec_not_public():
    spec = default_kaggle_mcp_spec()
    assert spec.public_endpoint is False
    assert spec.command == ["uvx", "kaggle-mcp-server"]


def test_kaggle_mcp_push_status_output_lifecycle():
    fake = FakeStdioClient(tools=[], call_results={
        "push_kernel": {"kernel_ref": "user/my-kernel"},
        "kernel_status": {"status": "complete"},
        "kernel_output": {"log": "done", "files": {"out.txt": "data"}},
    })
    client = KaggleMcpExecClient(client=fake)
    handle = client.push_kernel("/tmp/kerneldir")
    assert handle.kernel_ref == "user/my-kernel"

    status = client.get_status(handle)
    assert status.status == "complete"

    output = client.get_output(handle)
    assert output.ok
    assert output.log_text == "done"
    assert output.files["out.txt"] == "data"


def test_kaggle_mcp_push_kernel_raises_without_ref():
    fake = FakeStdioClient(tools=[], call_results={"push_kernel": {}})
    client = KaggleMcpExecClient(client=fake)
    with pytest.raises(MCPError):
        client.push_kernel("/tmp/kerneldir")


def test_kaggle_mcp_cancel_returns_false_on_mcp_error():
    fake = FakeStdioClient(tools=[], raise_on_call="kernel_cancel")
    client = KaggleMcpExecClient(client=fake)
    ok = client.cancel(KaggleKernelHandle(kernel_ref="user/my-kernel"))
    assert ok is False


def test_kaggle_mcp_close_stops_client():
    fake = FakeStdioClient(tools=[], call_results={"push_kernel": {"kernel_ref": "r"}})
    client = KaggleMcpExecClient(client=fake)
    client.push_kernel("/tmp/k")
    client.close()
    assert fake.stopped
