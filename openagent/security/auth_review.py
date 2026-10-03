"""Static, heuristic authentication/authorization review helpers.

This is a checklist assistant, not a replacement for a human security
review -- it flags patterns worth a human look, defensive-use only.
"""
from __future__ import annotations

import dataclasses
import re

_RISKY_PATTERNS = {
    "hardcoded_credential_check": re.compile(r"(?i)password\s*==\s*['\"]"),
    "logging_sensitive_value": re.compile(r"(?i)\b(log|print)\w*\s*\(.*\b(password|token|secret|api_key)\b"),
    "disabled_tls_verification": re.compile(r"(?i)verify\s*=\s*False"),
    "broad_except_around_auth": re.compile(r"(?i)except\s*:\s*\n\s*(pass|return True)"),
    "sql_string_concat": re.compile(r"(?i)(select|insert|update|delete)\b.*['\"]\s*\+"),
}


@dataclasses.dataclass
class AuthFinding:
    pattern: str
    line: int
    excerpt: str


def review_auth_code(text: str) -> list[AuthFinding]:
    findings = []
    lines = text.splitlines()
    for lineno, line in enumerate(lines, start=1):
        for name, pattern in _RISKY_PATTERNS.items():
            if pattern.search(line):
                findings.append(AuthFinding(pattern=name, line=lineno, excerpt=line.strip()[:160]))
    return findings
