"""Checksum verification utilities (streaming SHA-256, no full-file RAM load)."""
from __future__ import annotations

import hashlib
from pathlib import Path


class ChecksumMismatchError(RuntimeError):
    pass


def sha256_file(path: Path | str, chunk_size: int = 8 * 1024 * 1024) -> str:
    """Compute a file's SHA-256 digest while reading it in bounded-size chunks.

    Bounded chunk size keeps this safe on a low-RAM local PC even for
    multi-GB GGUF files.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def verify_file(path: Path | str, expected_sha256: str) -> bool:
    actual = sha256_file(path)
    return actual.lower() == expected_sha256.lower()


def verify_or_raise(path: Path | str, expected_sha256: str, label: str = "") -> None:
    actual = sha256_file(path)
    if actual.lower() != expected_sha256.lower():
        raise ChecksumMismatchError(
            f"Checksum mismatch for {label or path}: expected {expected_sha256}, got {actual}. "
            "Refusing to load model -- delete the file and re-download."
        )
