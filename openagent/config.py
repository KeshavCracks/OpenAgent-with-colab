"""Configuration loading and secret resolution.

Hard rules enforced here (see project README / docs/security.md):

* No API key, token, cookie, or credential is ever read from a committed
  YAML file. Checked-in config may only contain *references* of the form
  ``env:VAR_NAME`` or ``keyring:service:key`` (or the literal placeholder
  ``"CHANGE_ME"``). Any value that looks like a real secret is rejected by
  :func:`validate_no_literal_secrets`.
* The resolution order is: explicit overrides > environment variables >
  OS keyring (optional dependency) > user config file
  (``~/.config/openagent/config.yaml``) > repo defaults
  (``config/default.yaml``) > hard-coded fallbacks.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PLACEHOLDER_VALUES = {"CHANGE_ME", "REPLACE_ME", "", None}

# Patterns that look like *real* secrets accidentally pasted into a checked-in
# config file. This is intentionally conservative -- false positives are
# cheap, leaked tokens are not.
_SECRET_LOOKALIKE_PATTERNS = [
    re.compile(r"hf_[A-Za-z0-9]{20,}"),              # Hugging Face token
    re.compile(r"sk-[A-Za-z0-9]{20,}"),               # OpenAI-style key
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),       # GitHub token
    re.compile(r"AKIA[0-9A-Z]{16}"),                  # AWS access key id
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),     # Slack token
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
_PACKAGED_CONFIG_PATH = PACKAGE_ROOT / "config_default.yaml"
_REPO_CONFIG_PATH = REPO_ROOT / "config" / "default.yaml"
# Source checkouts keep the human-facing path (a symlink) for compatibility.
# A wheel cannot contain that repo-root path, so installed packages use the
# copy shipped inside the openagent package instead.
DEFAULT_CONFIG_PATH = (
    _REPO_CONFIG_PATH if _REPO_CONFIG_PATH.is_file() else _PACKAGED_CONFIG_PATH
)
USER_CONFIG_PATH = Path(os.environ.get(
    "OPENAGENT_CONFIG", str(Path.home() / ".config" / "openagent" / "config.yaml")
))
STATE_DIR = Path(os.environ.get("OPENAGENT_HOME", str(Path.home() / ".openagent")))


class SecretLeakError(RuntimeError):
    """Raised when a checked-in config file appears to contain a real secret."""


def validate_no_literal_secrets(text: str, source: str = "<config>") -> None:
    for pattern in _SECRET_LOOKALIKE_PATTERNS:
        m = pattern.search(text)
        if m:
            raise SecretLeakError(
                f"Refusing to load {source}: value resembling a real credential "
                f"was found ({pattern.pattern}). Use 'env:VAR_NAME' or "
                f"'keyring:service:key' references instead of literal secrets."
            )


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    validate_no_literal_secrets(text, source=str(path))
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must contain a mapping at top level")
    return data


def resolve_secret(ref: str | None) -> str | None:
    """Resolve a secret *reference* string to its value.

    Supported forms:
      - ``env:VAR_NAME``            -> os.environ['VAR_NAME']
      - ``keyring:service:key``     -> OS keyring entry (optional dep)
      - ``CHANGE_ME`` / "" / None   -> None (unset placeholder)
      - anything else is treated as a literal and rejected to avoid
        accidentally shipping a secret inline in code or config.
    """
    if ref is None or ref in PLACEHOLDER_VALUES:
        return None
    if ref.startswith("env:"):
        return os.environ.get(ref.split(":", 1)[1])
    if ref.startswith("keyring:"):
        try:
            import keyring  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "keyring reference used but the 'keyring' package is not installed. "
                "Install with: pip install openagent-harness[keyring]"
            ) from exc
        _, service, key = ref.split(":", 2)
        return keyring.get_password(service, key)
    validate_no_literal_secrets(ref, source="<secret reference>")
    raise ValueError(
        f"Unsupported secret reference {ref!r}. Use 'env:VAR_NAME' or "
        f"'keyring:service:key'."
    )


@dataclass
class ProviderLimits:
    max_session_hours: float = 12.0
    vram_gb: float = 15.0
    ram_gb: float = 12.0
    disk_gb: float = 70.0
    gpu: str = "T4"
    cpu_cores: int = 2
    weekly_gpu_quota_hours: float | None = None
    public_inbound_address: bool = False


@dataclass
class Config:
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, extra_overrides: dict | None = None) -> "Config":
        merged = _load_yaml(DEFAULT_CONFIG_PATH)
        merged = _deep_merge(merged, _load_yaml(USER_CONFIG_PATH))
        env_overrides = _env_overrides()
        merged = _deep_merge(merged, env_overrides)
        if extra_overrides:
            merged = _deep_merge(merged, extra_overrides)
        return cls(data=merged)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def secret(self, dotted_key: str) -> str | None:
        return resolve_secret(self.get(dotted_key))

    def provider_limits(self, provider: str) -> ProviderLimits:
        raw = self.get(f"providers.{provider}.limits", {}) or {}
        return ProviderLimits(**raw)


def _env_overrides() -> dict:
    """Translate OPENAGENT_SECTION__KEY=value env vars into a nested dict."""
    out: dict = {}
    prefix = "OPENAGENT__"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        path = key[len(prefix):].lower().split("__")
        node = out
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = value
    return out


def ensure_state_dirs() -> Path:
    for sub in ("sessions", "trajectories", "memory", "models_cache", "logs", "skills_cache"):
        (STATE_DIR / sub).mkdir(parents=True, exist_ok=True)
    return STATE_DIR
