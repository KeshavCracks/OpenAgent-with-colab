import hashlib

import pytest

from openagent.models.checksum import ChecksumMismatchError, sha256_file, verify_file, verify_or_raise


def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"some bytes" * 1000)
    expected = hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha256_file(p) == expected


def test_verify_file_true_on_match(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    expected = hashlib.sha256(b"abc").hexdigest()
    assert verify_file(p, expected) is True


def test_verify_file_false_on_mismatch(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    assert verify_file(p, "0" * 64) is False


def test_verify_or_raise_raises_on_mismatch(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    with pytest.raises(ChecksumMismatchError):
        verify_or_raise(p, "0" * 64)
