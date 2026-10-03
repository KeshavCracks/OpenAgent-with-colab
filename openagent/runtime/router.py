"""Multi-model router.

Enforces the project rule: only one large LLM is resident on the (free)
remote GPU at a time, and the harness switches models *by task phase*
(plan -> execute -> review -> ...), never per tool call, because multi-GB
reloads destroy latency. Small models (embeddings, decision router) may be
resident alongside the large one if their combined footprint is budgeted.
"""
from __future__ import annotations

import dataclasses
import time

from openagent.models.registry import ModelEntry, ModelRegistry, select_for_phase


class VramBudgetExceededError(RuntimeError):
    pass


@dataclasses.dataclass
class ResidentModel:
    entry: ModelEntry
    loaded_at: float
    role_tag: str  # "large" | "small"


class ModelRouter:
    def __init__(self, registry: ModelRegistry, vram_budget_gb: float):
        self.registry = registry
        self.vram_budget_gb = vram_budget_gb
        self._resident: dict[str, ResidentModel] = {}  # model_id -> ResidentModel
        self._current_phase: str | None = None
        self.swap_log: list[dict] = []

    def _footprint_gb(self, entry: ModelEntry) -> float:
        return (entry.raw.get("hardware", {}) or {}).get("min_vram_gb", 0) or 0

    def _is_large(self, entry: ModelEntry) -> bool:
        return self._footprint_gb(entry) >= 8  # small embedding/router models are <8GB

    def resident_ids(self) -> list[str]:
        return list(self._resident.keys())

    def current_vram_gb(self) -> float:
        return sum(self._footprint_gb(r.entry) for r in self._resident.values())

    def load_for_phase(self, phase: str) -> ModelEntry:
        entry = select_for_phase(self.registry, phase)
        if entry.id in self._resident:
            self._current_phase = phase
            return entry

        if self._is_large(entry):
            # Evict any other large model first -- never two large LLMs resident.
            for mid, res in list(self._resident.items()):
                if res.role_tag == "large":
                    self._unload(mid)

        projected = self.current_vram_gb() + self._footprint_gb(entry)
        if projected > self.vram_budget_gb:
            raise VramBudgetExceededError(
                f"Loading '{entry.id}' for phase '{phase}' would use {projected:.1f}GB "
                f"> budget {self.vram_budget_gb}GB. Free up a resident model first."
            )

        self._resident[entry.id] = ResidentModel(
            entry=entry, loaded_at=time.time(),
            role_tag="large" if self._is_large(entry) else "small",
        )
        self._current_phase = phase
        self.swap_log.append({"phase": phase, "loaded": entry.id, "t": time.time()})
        return entry

    def _unload(self, model_id: str) -> None:
        if model_id in self._resident:
            del self._resident[model_id]
            self.swap_log.append({"unloaded": model_id, "t": time.time()})

    def unload_all(self) -> None:
        for mid in list(self._resident.keys()):
            self._unload(mid)
