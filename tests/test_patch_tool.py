from pathlib import Path

import pytest

from openagent.tools.base import WorkspaceGuard
from openagent.tools.patch_tool import PatchError, PatchTool, apply_patch


def test_apply_simple_patch(tmp_path):
    (tmp_path / "f.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    guard = WorkspaceGuard(root=tmp_path)
    diff = (
        "--- a/f.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n def a():\n-    return 1\n+    return 2\n"
    )
    result = apply_patch(guard, diff)
    assert result["applied"] is True
    assert (tmp_path / "f.py").read_text() == "def a():\n    return 2\n"


def test_multi_file_patch(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
    guard = WorkspaceGuard(root=tmp_path)
    diff = (
        "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 100\n"
        "--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-y = 2\n+y = 200\n"
    )
    result = apply_patch(guard, diff)
    assert set(result["files"]) == {"a.py", "b.py"}
    assert (tmp_path / "a.py").read_text() == "x = 100\n"
    assert (tmp_path / "b.py").read_text() == "y = 200\n"


def test_patch_rejects_context_mismatch_without_corrupting_file(tmp_path):
    original = "def a():\n    return 1\n"
    (tmp_path / "f.py").write_text(original, encoding="utf-8")
    guard = WorkspaceGuard(root=tmp_path)
    # The context/deletion line doesn't match the real file content.
    bad_diff = (
        "--- a/f.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n def a():\n-    return 999\n+    return 2\n"
    )
    with pytest.raises(PatchError):
        apply_patch(guard, bad_diff)
    # File must be untouched -- no partial / corrupted write.
    assert (tmp_path / "f.py").read_text() == original


def test_patch_all_or_nothing_across_files(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
    guard = WorkspaceGuard(root=tmp_path)
    # Second file's hunk has a bad context line -- the whole patch must abort,
    # including the first (otherwise-valid) file's hunk.
    diff = (
        "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 100\n"
        "--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-y = 999\n+y = 200\n"
    )
    with pytest.raises(PatchError):
        apply_patch(guard, diff)
    assert (tmp_path / "a.py").read_text() == "x = 1\n"
    assert (tmp_path / "b.py").read_text() == "y = 2\n"


def test_patch_creates_new_file(tmp_path):
    guard = WorkspaceGuard(root=tmp_path)
    diff = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1,2 @@\n+x = 1\n+y = 2\n"
    result = apply_patch(guard, diff)
    assert result["applied"] is True
    assert (tmp_path / "new.py").read_text() == "x = 1\ny = 2\n"


def test_patch_deletes_file(tmp_path):
    (tmp_path / "old.py").write_text("x = 1\n", encoding="utf-8")
    guard = WorkspaceGuard(root=tmp_path)
    diff = "--- a/old.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x = 1\n"
    result = apply_patch(guard, diff)
    assert result["applied"] is True
    assert not (tmp_path / "old.py").exists()


def test_patch_dry_run_does_not_write(tmp_path):
    (tmp_path / "f.py").write_text("x = 1\n", encoding="utf-8")
    guard = WorkspaceGuard(root=tmp_path)
    diff = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    result = apply_patch(guard, diff, dry_run=True)
    assert result["applied"] is False
    assert (tmp_path / "f.py").read_text() == "x = 1\n"


def test_patch_tool_wrapper(tmp_path):
    (tmp_path / "f.py").write_text("x = 1\n", encoding="utf-8")
    guard = WorkspaceGuard(root=tmp_path)
    tool = PatchTool(guard)
    out = tool.run(diff="--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n")
    assert out["applied"] is True
