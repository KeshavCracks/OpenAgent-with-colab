"""Regex-based secret scanner for the defensive-security-review skill and the
pre-ship quality gate. Intentionally dependency-free (no network, no heavy
ML model) so it can run on every patch cheaply on a low-RAM machine."""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

PATTERNS: dict[str, re.Pattern] = {
    "huggingface_token": re.compile(r"hf_[A-Za-z0-9]{20,}"),
    "openai_style_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "aws_access_key_id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "generic_private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "kaggle_api_token": re.compile(r"KGAT_[A-Za-z0-9]{10,}"),
    "generic_assignment": re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*"
        r"['\"](?!env:|keyring:|CHANGE_ME|REPLACE_ME)[^'\"\s]{8,}['\"]"
    ),
}

SKIP_DIR_NAMES = {".git", "node_modules", ".venv", "__pycache__", "dist", "build"}


@dataclasses.dataclass
class SecretFinding:
    pattern: str
    path: str
    line: int
    excerpt: str


def scan_text(text: str, path_label: str = "<text>") -> list[SecretFinding]:
    findings = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for name, pattern in PATTERNS.items():
            if pattern.search(line):
                excerpt = line.strip()
                if len(excerpt) > 120:
                    excerpt = excerpt[:117] + "..."
                findings.append(SecretFinding(pattern=name, path=path_label, line=lineno, excerpt=excerpt))
    return findings


def scan_tree(root: Path | str, extensions: tuple[str, ...] | None = None) -> list[SecretFinding]:
    root = Path(root)
    findings: list[SecretFinding] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in p.parts):
            continue
        if extensions and p.suffix not in extensions:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(p.relative_to(root))
        findings.extend(scan_text(text, path_label=rel))
    return findings
