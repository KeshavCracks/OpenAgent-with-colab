"""Agent-facing wrapper around openagent.memory.store.MemoryStore."""
from __future__ import annotations

from openagent.memory.store import MemoryStore
from openagent.tools.base import Tool


class MemoryTool(Tool):
    name = "memory"
    description = (
        "Persist or recall small facts across sessions (project- or user-scoped). "
        "Never pass secrets, API keys, tokens, or cookies -- they are rejected."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["remember", "recall", "search", "forget"]},
            "scope": {"type": "string", "description": "e.g. 'project:myrepo' or 'user'"},
            "key": {"type": "string"},
            "value": {"type": "string"},
            "query": {"type": "string"},
            "record_id": {"type": "string"},
            "ttl_days": {"type": "number"},
            "confidence": {"type": "number"},
        },
        "required": ["action", "scope"],
    }
    permissions = ("memory:read", "memory:write")

    def __init__(self, store: MemoryStore, provenance: str = "agent"):
        self.store = store
        self.provenance = provenance

    def run(self, action: str, scope: str, key: str | None = None, value: str | None = None,
            query: str | None = None, record_id: str | None = None,
            ttl_days: float | None = None, confidence: float = 1.0):
        if action == "remember":
            if not key or value is None:
                raise ValueError("'key' and 'value' are required for action=remember")
            rec = self.store.remember(
                scope, key, value, provenance=self.provenance,
                confidence=confidence, ttl_days=ttl_days,
            )
            return rec.to_dict()
        if action == "recall":
            return {"records": [r.to_dict() for r in self.store.recall(scope, key)]}
        if action == "search":
            if not query:
                raise ValueError("'query' is required for action=search")
            return {"records": [r.to_dict() for r in self.store.search(scope, query)]}
        if action == "forget":
            if not record_id:
                raise ValueError("'record_id' is required for action=forget")
            return {"deleted": self.store.forget(record_id)}
        raise ValueError(f"Unknown action: {action}")
