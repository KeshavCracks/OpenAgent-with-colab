"""A lightweight persistent todo/task list tool, scoped to a session."""
from __future__ import annotations

import dataclasses
import json
import time
import uuid
from pathlib import Path

from openagent.tools.base import Tool


@dataclasses.dataclass
class TodoItem:
    id: str
    text: str
    status: str = "pending"  # pending | in_progress | done | cancelled
    created_at: float = dataclasses.field(default_factory=time.time)
    updated_at: float = dataclasses.field(default_factory=time.time)


class TodoStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8") or "[]")

    def _save(self, items: list[dict]) -> None:
        self.path.write_text(json.dumps(items, indent=2), encoding="utf-8")

    def add(self, text: str) -> TodoItem:
        items = self._load()
        item = TodoItem(id=str(uuid.uuid4())[:8], text=text)
        items.append(dataclasses.asdict(item))
        self._save(items)
        return item

    def update(self, item_id: str, status: str) -> dict:
        items = self._load()
        for it in items:
            if it["id"] == item_id:
                it["status"] = status
                it["updated_at"] = time.time()
                self._save(items)
                return it
        raise KeyError(f"No todo item with id {item_id}")

    def list(self) -> list[dict]:
        return self._load()


class TodoTool(Tool):
    name = "todo"
    description = "Manage a session-scoped todo list: add, update status, or list items."
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "update", "list"]},
            "text": {"type": "string"},
            "item_id": {"type": "string"},
            "status": {"type": "string", "enum": ["pending", "in_progress", "done", "cancelled"]},
        },
        "required": ["action"],
    }
    permissions = ("session:state",)

    def __init__(self, store: TodoStore):
        self.store = store

    def run(self, action: str, text: str | None = None, item_id: str | None = None, status: str | None = None):
        if action == "add":
            if not text:
                raise ValueError("'text' is required for action=add")
            return dataclasses.asdict(self.store.add(text))
        if action == "update":
            if not item_id or not status:
                raise ValueError("'item_id' and 'status' are required for action=update")
            return self.store.update(item_id, status)
        if action == "list":
            return {"items": self.store.list()}
        raise ValueError(f"Unknown action: {action}")
