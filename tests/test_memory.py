import time

import pytest

from openagent.memory.store import MemoryStore, SecretInMemoryError


def test_remember_and_recall():
    store = MemoryStore(":memory:")
    store.remember("project:x", "lang", "python", provenance="test")
    records = store.recall("project:x", "lang")
    assert len(records) == 1
    assert records[0].value == "python"


def test_search():
    store = MemoryStore(":memory:")
    store.remember("project:x", "fact1", "uses postgres", provenance="test")
    store.remember("project:x", "fact2", "uses redis", provenance="test")
    results = store.search("project:x", "postgres")
    assert len(results) == 1
    assert results[0].key == "fact1"


def test_forget():
    store = MemoryStore(":memory:")
    rec = store.remember("project:x", "k", "v", provenance="test")
    assert store.forget(rec.id) is True
    assert store.recall("project:x", "k") == []


def test_scopes_are_isolated():
    store = MemoryStore(":memory:")
    store.remember("project:a", "k", "v1", provenance="test")
    store.remember("project:b", "k", "v2", provenance="test")
    assert store.recall("project:a", "k")[0].value == "v1"
    assert store.recall("project:b", "k")[0].value == "v2"


@pytest.mark.parametrize("secret_value", [
    "my key is sk-abcdefghijklmnopqrstuvwxyz123456",
    "token: hf_abcdefghijklmnopqrstuvwxyz",
    "AKIAABCDEFGHIJKLMNOP is the access key",
    "-----BEGIN RSA PRIVATE KEY-----",
    "Authorization: Bearer abc123",
])
def test_remember_refuses_secrets(secret_value):
    store = MemoryStore(":memory:")
    with pytest.raises(SecretInMemoryError):
        store.remember("user", "secret", secret_value, provenance="test")


def test_remember_allows_non_secret_text():
    store = MemoryStore(":memory:")
    rec = store.remember("user", "preference", "prefers tabs over spaces", provenance="test")
    assert rec.value == "prefers tabs over spaces"


def test_ttl_expiry():
    store = MemoryStore(":memory:")
    rec = store.remember("user", "ephemeral", "value", provenance="test", ttl_days=0.0000001)
    time.sleep(0.1)
    assert store.recall("user", "ephemeral") == []
    assert store.recall("user", "ephemeral", include_expired=True) != []


def test_purge_expired():
    store = MemoryStore(":memory:")
    store.remember("user", "a", "v", provenance="test", ttl_days=0.0000001)
    store.remember("user", "b", "v", provenance="test", ttl_days=365)
    time.sleep(0.1)
    purged = store.purge_expired()
    assert purged == 1
    assert len(store.recall("user")) == 1
