"""Model registry: load, validate, and query pinned model entries.

The registry is the single source of truth for which model weights the
harness is allowed to download and run. It intentionally never stores model
*weights* -- only metadata, pinned revisions, and checksums (see
openagent/models/registry.yaml).
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Iterable

import yaml

REGISTRY_PATH = Path(__file__).resolve().parent / "registry.yaml"

REQUIRED_FIELDS = ["id", "role", "status", "source", "license", "benchmark_status"]
VALID_STATUS = {"reference_only", "available", "gated", "unavailable"}
VALID_ROLES = {
    "planner",
    "executor",
    "reviewer",
    "embedding",
    "speculative_draft",
    "decision_router",
}


class RegistryError(ValueError):
    pass


@dataclasses.dataclass
class ModelEntry:
    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def role(self) -> list[str]:
        r = self.raw.get("role", [])
        return r if isinstance(r, list) else [r]

    @property
    def status(self) -> str:
        return self.raw.get("status", "unavailable")

    @property
    def source(self) -> dict:
        return self.raw.get("source", {})

    @property
    def sha256(self) -> str | None:
        return self.source.get("sha256")

    @property
    def filename(self) -> str | None:
        return self.source.get("filename")

    @property
    def repo(self) -> str | None:
        return self.source.get("repo")

    @property
    def revision(self) -> str | None:
        return self.source.get("revision")

    @property
    def size_bytes(self) -> int | None:
        return self.source.get("size_bytes")

    @property
    def gate_passed(self) -> bool:
        return bool(self.raw.get("gate_passed", False))

    @property
    def requires_authenticated_download(self) -> bool:
        return bool(self.source.get("requires_authenticated_download", False))

    def fits(self, vram_gb: float, ram_gb: float) -> bool:
        hw = self.raw.get("hardware", {})
        min_vram = hw.get("min_vram_gb")
        min_ram = hw.get("min_ram_gb")
        if min_vram is not None and vram_gb < min_vram:
            return False
        if min_ram is not None and ram_gb < min_ram:
            return False
        return True

    def runtime_flags(self) -> dict:
        return dict(self.raw.get("runtime_flags", {}))

    def to_dict(self) -> dict:
        return self.raw


def _validate_entry(entry: dict) -> list[str]:
    errors = []
    for field_name in REQUIRED_FIELDS:
        if field_name not in entry:
            errors.append(f"model {entry.get('id', '<unknown>')}: missing field '{field_name}'")
    status = entry.get("status")
    if status is not None and status not in VALID_STATUS:
        errors.append(f"model {entry.get('id')}: invalid status '{status}'")
    roles = entry.get("role", [])
    roles = roles if isinstance(roles, list) else [roles]
    for r in roles:
        if r not in VALID_ROLES:
            errors.append(f"model {entry.get('id')}: invalid role '{r}'")
    source = entry.get("source", {})
    if entry.get("status") == "available" and source.get("format") == "gguf":
        if not source.get("sha256"):
            errors.append(f"model {entry.get('id')}: available GGUF entries must pin a sha256")
        if not source.get("revision"):
            errors.append(f"model {entry.get('id')}: available entries must pin a revision")
    return errors


class ModelRegistry:
    def __init__(self, data: dict):
        self.schema_version = data.get("schema_version")
        self.default_model_id = data.get("default_model_id")
        self._entries: dict[str, ModelEntry] = {
            m["id"]: ModelEntry(m) for m in data.get("models", [])
        }

    @classmethod
    def from_path(cls, path: Path | str = REGISTRY_PATH) -> "ModelRegistry":
        path = Path(path)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        errors: list[str] = []
        for m in data.get("models", []):
            errors.extend(_validate_entry(m))
        if errors:
            raise RegistryError("Model registry validation failed:\n" + "\n".join(errors))
        return cls(data)

    def all(self) -> list[ModelEntry]:
        return list(self._entries.values())

    def get(self, model_id: str) -> ModelEntry:
        if model_id not in self._entries:
            raise KeyError(f"Unknown model id: {model_id}")
        return self._entries[model_id]

    def default(self) -> ModelEntry:
        return self.get(self.default_model_id)

    def by_role(self, role: str) -> list[ModelEntry]:
        return [m for m in self.all() if role in m.role]

    def available(self) -> list[ModelEntry]:
        return [m for m in self.all() if m.status == "available"]

    def ids(self) -> list[str]:
        return list(self._entries.keys())


def load_registry(path: Path | str = REGISTRY_PATH) -> ModelRegistry:
    return ModelRegistry.from_path(path)


def select_for_phase(registry: ModelRegistry, phase: str) -> ModelEntry:
    """Pick the model entry for a harness task phase.

    Phases map to roles so the harness switches *by phase*, not per tool
    call, avoiding multi-GB reloads mid-task.
    """
    phase_to_role = {
        "plan": "planner",
        "execute": "executor",
        "review": "reviewer",
        "embed": "embedding",
        "route": "decision_router",
    }
    role = phase_to_role.get(phase)
    if role is None:
        raise ValueError(f"Unknown phase: {phase}")
    candidates = [m for m in registry.by_role(role) if m.status in ("available",)]
    if not candidates:
        raise RegistryError(f"No available model registered for phase '{phase}' (role={role})")
    # Prefer the configured default if it covers this role.
    default = registry.default()
    if default.id in [c.id for c in candidates]:
        return default
    return candidates[0]
