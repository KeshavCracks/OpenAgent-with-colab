"""Persistent agent memory: project-scoped and user-scoped, with provenance,
timestamps, confidence, TTL, redaction, and deletion.

Hard rule: secrets, credentials, private keys, and auth cookies are never
accepted into ordinary memory. `MemoryStore.remember()` scans every value and
raises :class:`SecretInMemoryError` rather than silently redacting, so the
caller (agent loop / CLI) must handle the rejection explicitly.
"""
from __future__ import annotations

import dataclasses
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from openagent.config import validate_no_literal_secrets, SecretLeakError

DEFAULT_TTL_DAYS = 180


class SecretInMemoryError(ValueError):
    pass


@dataclasses.dataclass
class MemoryRecord:
    id: str
    scope: str                 # "project:<name>" or "user"
    key: str
    value: str
    provenance: str
    created_at: float
    updated_at: float
    confidence: float = 1.0
    ttl_days: float | None = DEFAULT_TTL_DAYS
    tags: list[str] = dataclasses.field(default_factory=list)

    @property
    def expires_at(self) -> float | None:
        if self.ttl_days is None:
            return None
        return self.created_at + self.ttl_days * 86400

    def is_expired(self, now: float | None = None) -> bool:
        exp = self.expires_at
        if exp is None:
            return False
        return (now or time.time()) > exp

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["expires_at"] = self.expires_at
        return d


_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    provenance TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    ttl_days REAL,
    tags TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_memory_scope_key ON memory(scope, key);
"""


class MemoryStore:
    def __init__(self, db_path: Path | str = ":memory:"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _assert_no_secret(value: str) -> None:
        try:
            validate_no_literal_secrets(value, source="<memory value>")
        except SecretLeakError as exc:
            raise SecretInMemoryError(str(exc)) from exc
        lowered = value.lower()
        for banned in ("password:", "api_key:", "private key", "-----begin", "cookie:", "authorization: bearer"):
            if banned in lowered:
                raise SecretInMemoryError(
                    f"Refusing to store value that looks like a credential (matched {banned!r})"
                )

    def remember(
        self,
        scope: str,
        key: str,
        value: str,
        *,
        provenance: str,
        confidence: float = 1.0,
        ttl_days: float | None = DEFAULT_TTL_DAYS,
        tags: Optional[list[str]] = None,
    ) -> MemoryRecord:
        self._assert_no_secret(value)
        now = time.time()
        rec = MemoryRecord(
            id=str(uuid.uuid4()),
            scope=scope,
            key=key,
            value=value,
            provenance=provenance,
            created_at=now,
            updated_at=now,
            confidence=confidence,
            ttl_days=ttl_days,
            tags=tags or [],
        )
        self._conn.execute(
            "INSERT INTO memory (id, scope, key, value, provenance, created_at, updated_at, "
            "confidence, ttl_days, tags) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rec.id, rec.scope, rec.key, rec.value, rec.provenance, rec.created_at,
             rec.updated_at, rec.confidence, rec.ttl_days, json.dumps(rec.tags)),
        )
        self._conn.commit()
        return rec

    def recall(self, scope: str, key: str | None = None, include_expired: bool = False) -> list[MemoryRecord]:
        if key is not None:
            cur = self._conn.execute(
                "SELECT * FROM memory WHERE scope=? AND key=? ORDER BY updated_at DESC", (scope, key)
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM memory WHERE scope=? ORDER BY updated_at DESC", (scope,)
            )
        records = [self._row_to_record(r) for r in cur.fetchall()]
        if not include_expired:
            records = [r for r in records if not r.is_expired()]
        return records

    def search(self, scope: str, query: str) -> list[MemoryRecord]:
        like = f"%{query}%"
        cur = self._conn.execute(
            "SELECT * FROM memory WHERE scope=? AND (key LIKE ? OR value LIKE ?) "
            "ORDER BY updated_at DESC",
            (scope, like, like),
        )
        return [self._row_to_record(r) for r in cur.fetchall() if not self._row_to_record(r).is_expired()]

    def forget(self, record_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM memory WHERE id=?", (record_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def purge_expired(self) -> int:
        now = time.time()
        cur = self._conn.execute(
            "DELETE FROM memory WHERE ttl_days IS NOT NULL AND (created_at + ttl_days * 86400) < ?",
            (now,),
        )
        self._conn.commit()
        return cur.rowcount

    def _row_to_record(self, row: tuple) -> MemoryRecord:
        (id_, scope, key, value, provenance, created_at, updated_at,
         confidence, ttl_days, tags) = row
        return MemoryRecord(
            id=id_, scope=scope, key=key, value=value, provenance=provenance,
            created_at=created_at, updated_at=updated_at, confidence=confidence,
            ttl_days=ttl_days, tags=json.loads(tags),
        )
