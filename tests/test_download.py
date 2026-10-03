import hashlib
from pathlib import Path

import pytest

from openagent.models.checksum import ChecksumMismatchError
from openagent.models.download import DownloadError, download_model
from openagent.models.registry import ModelEntry


def _entry(**overrides) -> ModelEntry:
    content = b"fake-model-bytes"
    sha256 = hashlib.sha256(content).hexdigest()
    raw = {
        "id": "fake-model",
        "status": "available",
        "source": {
            "repo": "someorg/somerepo",
            "revision": "deadbeef",
            "filename": "model.gguf",
            "sha256": sha256,
        },
    }
    raw.update(overrides)
    return ModelEntry(raw), content


def test_download_verifies_checksum(tmp_path):
    entry, content = _entry()

    def fake_fetcher(url, dest, token, on_progress):
        dest.write_bytes(content)
        on_progress(len(content), len(content))

    result = download_model(entry, tmp_path, fetcher=fake_fetcher)
    assert result.verified is True
    assert result.path.read_bytes() == content


def test_download_rejects_checksum_mismatch(tmp_path):
    entry, _ = _entry()

    def bad_fetcher(url, dest, token, on_progress):
        dest.write_bytes(b"wrong-bytes")

    with pytest.raises(ChecksumMismatchError):
        download_model(entry, tmp_path, fetcher=bad_fetcher)


def test_download_requires_token_for_gated_model(tmp_path):
    entry, _ = _entry()
    entry.raw["source"]["requires_authenticated_download"] = True

    def fetcher(url, dest, token, on_progress):
        raise AssertionError("fetcher should not be called without a token")

    with pytest.raises(DownloadError):
        download_model(entry, tmp_path, fetcher=fetcher, token=None)


def test_download_skips_existing_verified_file(tmp_path):
    entry, content = _entry()
    dest = tmp_path / "model.gguf"
    dest.write_bytes(content)

    def fetcher(url, dest, token, on_progress):
        raise AssertionError("should not re-download an already-verified file")

    result = download_model(entry, tmp_path, fetcher=fetcher)
    assert result.skipped_existing is True


def test_download_without_pinned_sha256_refuses(tmp_path):
    entry, _ = _entry()
    entry.raw["source"]["sha256"] = None

    def fetcher(url, dest, token, on_progress):
        raise AssertionError("should not download without a pinned checksum")

    with pytest.raises(DownloadError):
        download_model(entry, tmp_path, fetcher=fetcher)
