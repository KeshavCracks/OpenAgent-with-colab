"""Open Viking-style context system.

Gives the agent controlled, ranked, redacted access to: repository files,
docs, issues, memory, skills, prior trajectories, and runtime state --
through one uniform query surface with a hard context budget, instead of
dumping everything into the prompt.
"""
from __future__ import annotations

import dataclasses
import re
import time
from typing import Callable

from openagent.agent.context import estimate_tokens
from openagent.security.secret_scan import scan_text


@dataclasses.dataclass
class ContextItem:
    source: str
    identifier: str
    content: str
    provenance: str
    relevance_score: float = 0.0
    redacted: bool = False
    fetched_at: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


SourceFn = Callable[[str], list[ContextItem]]


@dataclasses.dataclass
class ContextSource:
    name: str
    fetch: SourceFn
    enabled: bool = True


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9_\-\.]+", text.lower()))


def _score(query_tokens: set[str], item: ContextItem) -> float:
    item_tokens = _tokenize(item.content)
    if not item_tokens:
        return 0.0
    overlap = query_tokens & item_tokens
    return len(overlap) / max(1, len(query_tokens))


def _redact(item: ContextItem) -> ContextItem:
    findings = scan_text(item.content, path_label=item.identifier)
    if not findings:
        return item
    redacted_lines = item.content.splitlines()
    for f in findings:
        if 0 < f.line <= len(redacted_lines):
            redacted_lines[f.line - 1] = "[REDACTED: possible credential removed by context system]"
    return dataclasses.replace(item, content="\n".join(redacted_lines), redacted=True)


class OpenVikingContext:
    def __init__(self, max_context_tokens: int = 4000):
        self.sources: dict[str, ContextSource] = {}
        self.max_context_tokens = max_context_tokens

    def register_source(self, source: ContextSource) -> None:
        self.sources[source.name] = source

    def query(self, query_text: str, top_k: int = 10, source_names: list[str] | None = None) -> list[ContextItem]:
        query_tokens = _tokenize(query_text)
        all_items: list[ContextItem] = []
        names = source_names or [n for n, s in self.sources.items() if s.enabled]
        for name in names:
            source = self.sources.get(name)
            if not source or not source.enabled:
                continue
            for item in source.fetch(query_text):
                item.relevance_score = _score(query_tokens, item)
                all_items.append(_redact(item))

        all_items.sort(key=lambda i: i.relevance_score, reverse=True)

        selected: list[ContextItem] = []
        budget_used = 0
        for item in all_items:
            if len(selected) >= top_k:
                break
            cost = estimate_tokens([{"role": "system", "content": item.content}])
            if budget_used + cost > self.max_context_tokens:
                continue
            selected.append(item)
            budget_used += cost
        return selected

    def budget_report(self, items: list[ContextItem]) -> dict:
        used = sum(estimate_tokens([{"role": "system", "content": i.content}]) for i in items)
        return {"items": len(items), "tokens_used": used, "tokens_budget": self.max_context_tokens}
