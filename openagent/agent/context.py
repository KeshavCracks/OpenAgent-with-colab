"""Context window budgeting and summarization.

Approximates token count with a cheap 4-chars-per-token heuristic (good
enough for budgeting decisions; the server-side tokenizer is authoritative
for the actual request). When the running total crosses `soft_limit_tokens`,
older turns are collapsed into a single summary message using an injectable
`summarizer` callable, keeping the most recent turns verbatim.
"""
from __future__ import annotations

import dataclasses
from typing import Callable, Optional

CHARS_PER_TOKEN = 4

Summarizer = Callable[[list[dict]], str]


def estimate_tokens(messages: list[dict]) -> int:
    total_chars = 0
    for m in messages:
        content = m.get("content") or ""
        if isinstance(content, list):  # vision-style content parts
            content = " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        total_chars += len(str(content))
        for tc in m.get("tool_calls") or []:
            total_chars += len(str(tc))
    return max(1, total_chars // CHARS_PER_TOKEN)


def _default_summarizer(messages: list[dict]) -> str:
    """Extractive fallback summarizer (no model call) -- deterministic and
    offline, used when no LLM-backed summarizer is wired up (e.g. in tests
    or before a session has a healthy model endpoint)."""
    bullet_lines = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content") or ""
        if isinstance(content, list):
            content = " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        content = str(content).strip().replace("\n", " ")
        if content:
            bullet_lines.append(f"- [{role}] {content[:160]}")
    return "Summary of earlier conversation (auto-condensed):\n" + "\n".join(bullet_lines[-30:])


@dataclasses.dataclass
class ContextBudget:
    soft_limit_tokens: int = 6000
    hard_limit_tokens: int = 8000
    keep_recent_turns: int = 6
    summarize_when_over: bool = True

    def over_soft_limit(self, messages: list[dict]) -> bool:
        return estimate_tokens(messages) > self.soft_limit_tokens

    def over_hard_limit(self, messages: list[dict]) -> bool:
        return estimate_tokens(messages) > self.hard_limit_tokens


class ContextManager:
    def __init__(self, budget: ContextBudget, summarizer: Optional[Summarizer] = None):
        self.budget = budget
        self.summarizer = summarizer or _default_summarizer
        self.summarization_events: list[dict] = []

    def maybe_compact(self, messages: list[dict]) -> list[dict]:
        if not self.budget.summarize_when_over or not self.budget.over_soft_limit(messages):
            return messages

        system_messages = [m for m in messages if m.get("role") == "system"]
        rest = [m for m in messages if m.get("role") != "system"]
        if len(rest) <= self.budget.keep_recent_turns:
            return messages  # nothing worth compacting yet

        to_summarize = rest[: -self.budget.keep_recent_turns]
        to_keep = rest[-self.budget.keep_recent_turns:]
        summary_text = self.summarizer(to_summarize)
        summary_message = {"role": "system", "content": summary_text, "_openagent_summary": True}

        compacted = system_messages + [summary_message] + to_keep
        self.summarization_events.append({
            "summarized_count": len(to_summarize),
            "kept_count": len(to_keep),
            "tokens_before": estimate_tokens(messages),
            "tokens_after": estimate_tokens(compacted),
        })
        return compacted
