"""Regression tests for files that must survive wheel packaging."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path


def test_wheel_contains_runtime_data(tmp_path):
    """Build a wheel and verify every runtime data file is included."""
    repo_root = Path(__file__).resolve().parent.parent
    wheel_dir = tmp_path / "dist"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--outdir",
            str(wheel_dir),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    wheels = sorted(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        packaged_files = set(archive.namelist())

    expected_files = {
        "openagent/config_default.yaml",
        "openagent/models/registry.yaml",
    }
    expected_files.update(
        path.relative_to(repo_root).as_posix()
        for path in (repo_root / "openagent" / "skills" / "catalog").rglob("*")
        if path.is_file() and path.suffix in {".yaml", ".md"}
    )

    assert expected_files <= packaged_files
