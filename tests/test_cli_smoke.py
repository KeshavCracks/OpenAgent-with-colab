import json

from openagent.cli import main


def _run(capsys, argv):
    code = main(argv)
    out = capsys.readouterr().out
    return code, out


def test_cli_models_list(capsys):
    code, out = _run(capsys, ["models", "list"])
    assert code == 0
    data = json.loads(out)
    assert data["default"] == "qwen3.8-27b-gguf-q4km"


def test_cli_models_show(capsys):
    code, out = _run(capsys, ["models", "show", "qwen3.8-27b-gguf-q4km"])
    assert code == 0
    data = json.loads(out)
    assert data["id"] == "qwen3.8-27b-gguf-q4km"


def test_cli_skills_list(capsys):
    code, out = _run(capsys, ["skills", "list"])
    assert code == 0
    data = json.loads(out)
    assert any(s["name"] == "defensive-security-review" for s in data)


def test_cli_skills_find(capsys):
    code, out = _run(capsys, ["skills", "find", "please review this for security secrets"])
    assert code == 0
    data = json.loads(out)
    assert data[0]["name"] == "defensive-security-review"


def test_cli_benchmark_run(capsys):
    code, out = _run(capsys, ["benchmark", "run", "--model-id", "cli-test"])
    assert code == 0
    results = json.loads(out)
    assert all(r["passed"] for r in results)


def test_cli_security_secret_scan_clean_dir(tmp_path, capsys, monkeypatch):
    (tmp_path / "clean.py").write_text("x = 1\n", encoding="utf-8")
    code, out = _run(capsys, ["security", "secret-scan", str(tmp_path)])
    assert code == 0
    assert json.loads(out) == []


def test_cli_security_secret_scan_detects(tmp_path, capsys):
    (tmp_path / "leak.py").write_text('API_KEY = "sk-realistictoken1234567890123456"', encoding="utf-8")
    code, out = _run(capsys, ["security", "secret-scan", str(tmp_path)])
    assert code == 1
    findings = json.loads(out)
    assert len(findings) >= 1
    assert all(f["path"] == "leak.py" for f in findings)


def test_cli_new_session_and_list(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    code, out = _run(capsys, ["new", "--workspace", str(tmp_path)])
    assert code == 0
    meta = json.loads(out)
    assert meta["status"] == "created"

    code, out = _run(capsys, ["sessions"])
    assert code == 0
    sessions = json.loads(out)
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == meta["session_id"]


def test_cli_memory_roundtrip(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    code, out = _run(capsys, ["memory", "remember", "project:x", "lang", "python"])
    assert code == 0

    code, out = _run(capsys, ["memory", "recall", "project:x", "lang"])
    assert code == 0
    records = json.loads(out)
    assert records[0]["value"] == "python"


def test_cli_memory_refuses_secret(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    code, _ = _run(capsys, ["memory", "remember", "user", "key", "sk-realistictoken1234567890123456"])
    assert code == 3


def test_cli_providers_bootstrap_colab(tmp_path, capsys):
    out_dir = tmp_path / "colab_out"
    code, out = _run(capsys, ["providers", "bootstrap", "colab", "qwen3.8-27b-gguf-q4km", "--out-dir", str(out_dir)])
    assert code == 0
    data = json.loads(out)
    assert len(data["generated_files"]) == 2
    for f in data["generated_files"]:
        assert (tmp_path / "colab_out").exists()


def test_cli_providers_bootstrap_kaggle(tmp_path, capsys):
    out_dir = tmp_path / "kaggle_out"
    code, out = _run(capsys, ["providers", "bootstrap", "kaggle", "qwen3.8-27b-gguf-q4km", "--out-dir", str(out_dir)])
    assert code == 0
    data = json.loads(out)
    assert len(data["generated_files"]) == 2


def test_cli_mcp_list_includes_v1_builtin_tools(capsys):
    code, out = _run(capsys, ["mcp", "list"])
    assert code == 0
    data = json.loads(out)
    for expected in ("read", "glob", "grep", "patch", "shell", "todo", "memory", "skills"):
        assert expected in data["builtin_tools"]


def test_cli_models_verify_matches(tmp_path, capsys):
    from openagent.models.registry import load_registry

    entry = load_registry().get("qwen3.8-27b-gguf-q4km")
    f = tmp_path / "fake_model.gguf"
    f.write_bytes(b"not a real model file")
    code, out = _run(capsys, ["models", "verify", entry.id, str(f)])
    assert code == 1  # content doesn't match the pinned sha256
    data = json.loads(out)
    assert data["ok"] is False
    assert data["expected_sha256"] == entry.sha256


def test_cli_research_doctor_reports_all_unavailable_without_sessions(capsys):
    code, out = _run(capsys, ["research", "doctor"])
    assert code == 0
    statuses = json.loads(out)
    assert len(statuses) > 0


def test_cli_schedule_add_list_tick(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    code, out = _run(capsys, ["schedule", "add", "nightly", "3600", "shell:pytest -q"])
    assert code == 0
    task = json.loads(out)

    code, out = _run(capsys, ["schedule", "list"])
    assert code == 0
    tasks = json.loads(out)
    assert tasks[0]["id"] == task["id"]

    code, out = _run(capsys, ["schedule", "tick"])
    assert code == 0
    results = json.loads(out)
    assert results[0]["task_id"] == task["id"]


def test_cli_trajectory_show_summarizes_events(tmp_path, capsys, monkeypatch):
    from openagent.agent.trajectory import TrajectoryRecorder

    monkeypatch.setenv("HOME", str(tmp_path))
    traj_dir = tmp_path / ".openagent" / "trajectories"
    recorder = TrajectoryRecorder(traj_dir / "sess1.jsonl", "sess1")
    recorder.record_message("user", "hello")
    recorder.record_tool_call("read", {"path": "a.txt"}, {"content": "x"}, True, 5.0)
    recorder.record_message("assistant", "done")

    code, out = _run(capsys, ["trajectory", "show", "sess1"])
    assert code == 0
    summary = json.loads(out)
    assert summary["total_events"] == 3

    code, out = _run(capsys, ["trajectory", "show", "sess1", "--tool-calls-only"])
    assert code == 0
    details = json.loads(out)
    assert len(details) == 1
    assert details[0]["tool"] == "read"
