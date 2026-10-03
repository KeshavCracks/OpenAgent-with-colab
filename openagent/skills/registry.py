"""Skill registry: loads skill manifests with progressive disclosure.

Every skill is described by a small YAML manifest (cheap to keep in every
prompt as a one-line summary) plus an optional `body` file (SKILL.md or
similar) that is only loaded into context once a skill is actually selected
-- this is the "progressive disclosure" rule: skills must not flood every
prompt with their full instructions.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"


@dataclasses.dataclass
class SkillManifest:
    raw: dict[str, Any]
    manifest_path: Path

    @property
    def name(self) -> str:
        return self.raw["name"]

    @property
    def version(self) -> str:
        return self.raw.get("version", "0.0.0")

    @property
    def summary(self) -> str:
        return self.raw.get("summary", "")

    @property
    def triggers(self) -> list[str]:
        return [t.lower() for t in self.raw.get("triggers", [])]

    @property
    def required_tools(self) -> list[str]:
        return self.raw.get("required_tools", [])

    @property
    def required_permissions(self) -> list[str]:
        return self.raw.get("required_permissions", [])

    @property
    def context_budget_tokens(self) -> int:
        return int(self.raw.get("context_budget_tokens", 500))

    @property
    def source(self) -> dict:
        return self.raw.get("source", {})

    @property
    def license(self) -> str:
        return self.raw.get("license", "unknown")

    @property
    def verification_procedure(self) -> list[str]:
        return self.raw.get("verification_procedure", [])

    @property
    def lifecycle(self) -> list[str]:
        return self.raw.get("lifecycle", [])

    @property
    def quality_gates(self) -> list[str]:
        return self.raw.get("quality_gates", [])

    @property
    def body_file(self) -> str | None:
        return self.raw.get("body_file")

    def load_body(self) -> str:
        """Load the full skill body (SKILL.md-equivalent) on demand only."""
        if not self.body_file:
            return ""
        body_path = self.manifest_path.parent / self.body_file
        return body_path.read_text(encoding="utf-8")

    def to_summary_dict(self) -> dict:
        """What goes in every prompt: tiny, not the full instructions."""
        return {
            "name": self.name,
            "version": self.version,
            "summary": self.summary,
            "triggers": self.raw.get("triggers", []),
            "context_budget_tokens": self.context_budget_tokens,
        }


class SkillRegistry:
    def __init__(self, catalog_dir: Path | str = CATALOG_DIR):
        self.catalog_dir = Path(catalog_dir)
        self._skills: dict[str, SkillManifest] = {}
        self._load_all()

    def _load_all(self) -> None:
        for manifest_path in sorted(self.catalog_dir.glob("*/skill.yaml")):
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            skill = SkillManifest(raw=data, manifest_path=manifest_path)
            self._skills[skill.name] = skill

    def all(self) -> list[SkillManifest]:
        return list(self._skills.values())

    def get(self, name: str) -> SkillManifest:
        return self._skills[name]

    def names(self) -> list[str]:
        return list(self._skills.keys())

    def catalog_summary(self) -> list[dict]:
        """The progressive-disclosure view suitable for embedding in a prompt."""
        return [s.to_summary_dict() for s in self._skills.values()]

    def total_catalog_context_tokens(self) -> int:
        return sum(s.context_budget_tokens for s in self._skills.values())
