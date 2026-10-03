import pytest

from openagent.config import SecretLeakError, resolve_secret, validate_no_literal_secrets


def test_placeholder_values_resolve_to_none():
    assert resolve_secret(None) is None
    assert resolve_secret("") is None
    assert resolve_secret("CHANGE_ME") is None


def test_env_reference_resolves(monkeypatch):
    monkeypatch.setenv("MY_TEST_TOKEN", "value123")
    assert resolve_secret("env:MY_TEST_TOKEN") == "value123"


def test_env_reference_missing_returns_none(monkeypatch):
    monkeypatch.delenv("DOES_NOT_EXIST_XYZ", raising=False)
    assert resolve_secret("env:DOES_NOT_EXIST_XYZ") is None


@pytest.mark.parametrize("literal", [
    "hf_abcdefghijklmnopqrstuvwxyz",
    "sk-abcdefghijklmnopqrstuvwxyz123456",
    "ghp_abcdefghijklmnopqrstuvwxyz123456",
    "AKIAABCDEFGHIJKLMNOP",
])
def test_validate_no_literal_secrets_rejects_real_looking_tokens(literal):
    with pytest.raises(SecretLeakError):
        validate_no_literal_secrets(literal)


def test_validate_no_literal_secrets_allows_placeholders():
    validate_no_literal_secrets("api_key: env:HF_TOKEN")
    validate_no_literal_secrets("token: CHANGE_ME")


def test_resolve_secret_rejects_unsupported_literal():
    with pytest.raises(ValueError):
        resolve_secret("just-some-literal-value")
