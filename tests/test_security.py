import json
from pathlib import Path

import pytest

from openagent.security.auth_review import review_auth_code
from openagent.security.dep_audit import run_dependency_audit
from openagent.security.secret_scan import scan_text, scan_tree


def test_scan_text_detects_hf_token():
    findings = scan_text('HF_TOKEN = "hf_abcdefghijklmnopqrstuvwxyz"')
    assert any(f.pattern == "huggingface_token" for f in findings)


def test_scan_text_detects_private_key():
    findings = scan_text("-----BEGIN RSA PRIVATE KEY-----\nMIIexxxx\n")
    assert any(f.pattern == "generic_private_key" for f in findings)


def test_scan_text_allows_env_reference():
    findings = scan_text('api_key: "env:KAGGLE_KEY"')
    assert findings == []


def test_scan_text_allows_placeholder():
    findings = scan_text('token: "CHANGE_ME"')
    assert findings == []


def test_scan_text_flags_hardcoded_literal():
    findings = scan_text('password: "hunter2hunter2"')
    assert any(f.pattern == "generic_assignment" for f in findings)


def test_scan_tree_walks_files_and_skips_vcs_dirs(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("sk-shouldnotbefound00000000000000000", encoding="utf-8")
    (tmp_path / "app.py").write_text('API_KEY = "sk-realistictoken1234567890123456"', encoding="utf-8")
    findings = scan_tree(tmp_path)
    paths = {f.path for f in findings}
    assert "app.py" in paths
    assert not any(".git" in p for p in paths)


def test_dep_audit_reports_tool_missing_gracefully(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    result = run_dependency_audit(tmp_path, ecosystem="python")
    assert result.tool_available is False
    assert result.error


def test_dep_audit_python_success_path_parses_vulnerabilities(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/pip-audit")

    class FakeCompletedProcess:
        stdout = json.dumps([{"name": "requests", "version": "2.0.0", "vulns": ["CVE-123"]}])

    monkeypatch.setattr("openagent.security.dep_audit._run", lambda cmd, cwd, timeout=120: FakeCompletedProcess())
    result = run_dependency_audit(tmp_path, ecosystem="python")
    assert result.tool_available is True
    assert result.vulnerabilities[0]["name"] == "requests"
    assert result.error is None


def test_dep_audit_node_success_path_parses_vulnerabilities(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/npm")

    class FakeCompletedProcess:
        stdout = json.dumps({"vulnerabilities": {"lodash": {"severity": "high"}}})

    monkeypatch.setattr("openagent.security.dep_audit._run", lambda cmd, cwd, timeout=120: FakeCompletedProcess())
    result = run_dependency_audit(tmp_path, ecosystem="node")
    assert result.tool_available is True
    assert result.vulnerabilities[0]["severity"] == "high"


def test_dep_audit_unsupported_ecosystem_raises(tmp_path):
    with pytest.raises(ValueError):
        run_dependency_audit(tmp_path, ecosystem="rust")


def test_auth_review_flags_hardcoded_password_check():
    code = 'if password == "letmein":\n    return True\n'
    findings = review_auth_code(code)
    assert any(f.pattern == "hardcoded_credential_check" for f in findings)


def test_auth_review_flags_logging_secret():
    code = 'print("token is", token)\n'
    findings = review_auth_code(code)
    assert any(f.pattern == "logging_sensitive_value" for f in findings)


def test_auth_review_clean_code_has_no_findings():
    code = "def add(a, b):\n    return a + b\n"
    assert review_auth_code(code) == []
