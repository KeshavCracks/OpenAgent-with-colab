"""Download and checksum-verify model files from the Hugging Face Hub.

Designed for a low-RAM local PC *or* an ephemeral Colab/Kaggle container:
streams to disk in bounded chunks, verifies sha256 before declaring success,
and never silently falls back to an unpinned revision.
"""
from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Callable, Optional

from openagent.models.checksum import ChecksumMismatchError, verify_or_raise
from openagent.models.registry import ModelEntry

HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://huggingface.co")


@dataclasses.dataclass
class DownloadResult:
    path: Path
    sha256: str
    bytes_downloaded: int
    verified: bool
    skipped_existing: bool = False


class DownloadError(RuntimeError):
    pass


def resolve_url(entry: ModelEntry) -> str:
    if not entry.repo or not entry.filename:
        raise DownloadError(
            f"Model {entry.id} has no single-file source (repo/filename) to download; "
            "it is likely a multi-shard safetensors reference entry -- see manifest_url."
        )
    revision = entry.revision or "main"
    return f"{HF_ENDPOINT}/{entry.repo}/resolve/{revision}/{entry.filename}"


# A "fetcher" is injectable for tests / alternate transports (e.g. aria2c).
Fetcher = Callable[[str, Path, Optional[str], Callable[[int, int | None], None]], None]


def _default_fetcher(url: str, dest: Path, token: str | None, on_progress) -> None:
    import requests  # imported lazily so the module is importable w/o network stack

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, headers=headers, stream=True, timeout=30) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0)) or None
        downloaded = 0
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                on_progress(downloaded, total)
    tmp.rename(dest)


def download_model(
    entry: ModelEntry,
    dest_dir: Path | str,
    *,
    token: str | None = None,
    fetcher: Fetcher = _default_fetcher,
    on_progress: Callable[[int, int | None], None] | None = None,
    force: bool = False,
) -> DownloadResult:
    """Download `entry`'s pinned file into dest_dir and verify its checksum.

    Raises ChecksumMismatchError / DownloadError rather than returning a
    "maybe ok" result -- callers (CLI, provider bootstrap scripts) must treat
    any exception as a hard stop before the model is ever loaded.
    """
    if entry.status == "gated" and not entry.requires_authenticated_download:
        pass  # metadata inconsistency, non-fatal
    if entry.requires_authenticated_download and not token:
        raise DownloadError(
            f"Model {entry.id} is gated and requires an authenticated Hugging Face "
            "token that has accepted the repository's access terms. Set HF_TOKEN."
        )
    if not entry.sha256:
        raise DownloadError(
            f"Model {entry.id} has no pinned sha256 in the registry -- refusing to "
            "download an unverifiable file."
        )

    dest_dir = Path(dest_dir)
    dest_path = dest_dir / Path(entry.filename).name

    if dest_path.exists() and not force:
        try:
            verify_or_raise(dest_path, entry.sha256, label=entry.id)
            return DownloadResult(
                path=dest_path,
                sha256=entry.sha256,
                bytes_downloaded=dest_path.stat().st_size,
                verified=True,
                skipped_existing=True,
            )
        except ChecksumMismatchError:
            dest_path.unlink()  # corrupt/stale cache, re-download

    url = resolve_url(entry)
    progress_cb = on_progress or (lambda done, total: None)
    fetcher(url, dest_path, token, progress_cb)

    verify_or_raise(dest_path, entry.sha256, label=entry.id)
    return DownloadResult(
        path=dest_path,
        sha256=entry.sha256,
        bytes_downloaded=dest_path.stat().st_size,
        verified=True,
    )
