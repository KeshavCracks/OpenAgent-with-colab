"""Session lifecycle: create, resume, list, and stop harness sessions.

Each session owns: a workspace root, a trajectory file, a message history,
and (once started) a provider session tying it to a remote GPU backend. The
CLI's `openagent new` / `openagent sessions` commands are thin wrappers
around this module.
"""
from __future__ import annotations

import dataclasses
import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional


@dataclasses.dataclass
class SessionMeta:
    session_id: str
    workspace: str
    created_at: float
    mode: str = "local-workspace-remote-inference"
    provider: str | None = None
    model_id: str | None = None
    status: str = "created"   # created | running | stopped | expired | failed
    parent_session_id: str | None = None   # set for subagent sessions
    messages: list[dict] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class SessionStore:
    def __init__(self, sessions_dir: Path | str):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def create(self, workspace: str, mode: str = "local-workspace-remote-inference",
               parent_session_id: str | None = None) -> SessionMeta:
        meta = SessionMeta(
            session_id=str(uuid.uuid4())[:12], workspace=workspace,
            created_at=time.time(), mode=mode, parent_session_id=parent_session_id,
        )
        self.save(meta)
        return meta

    def save(self, meta: SessionMeta) -> None:
        self._path(meta.session_id).write_text(json.dumps(meta.to_dict(), indent=2), encoding="utf-8")

    def load(self, session_id: str) -> SessionMeta:
        data = json.loads(self._path(session_id).read_text(encoding="utf-8"))
        return SessionMeta(**data)

    def list(self) -> list[SessionMeta]:
        out = []
        for p in sorted(self.sessions_dir.glob("*.json")):
            out.append(SessionMeta(**json.loads(p.read_text(encoding="utf-8"))))
        return out

    def stop(self, session_id: str) -> SessionMeta:
        meta = self.load(session_id)
        meta.status = "stopped"
        self.save(meta)
        return meta

    def delete(self, session_id: str) -> bool:
        p = self._path(session_id)
        if p.exists():
            p.unlink()
            return True
        return False
