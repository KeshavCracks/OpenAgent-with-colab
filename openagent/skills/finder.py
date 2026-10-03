"""Skill-finder: recommend the right skill(s) for a task without flooding
the prompt with every skill's full instructions.

Scoring is a transparent, debuggable keyword/trigger match (no network call,
no extra model invocation needed just to pick a skill) so it stays cheap
enough to run on every task on a low-RAM local PC. The caller only pays the
`context_budget_tokens` cost for skills that are actually recommended.
"""
from __future__ import annotations

import dataclasses
import re

from openagent.skills.registry import SkillManifest, SkillRegistry


@dataclasses.dataclass
class SkillMatch:
    skill: SkillManifest
    score: float
    matched_triggers: list[str]


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9_\-\.]+", text.lower()))


def find_skills(
    registry: SkillRegistry,
    task_description: str,
    top_k: int = 3,
    min_score: float = 0.01,
) -> list[SkillMatch]:
    task_tokens = _tokenize(task_description)
    task_lower = task_description.lower()
    matches: list[SkillMatch] = []
    for skill in registry.all():
        matched = []
        score = 0.0
        for trigger in skill.triggers:
            trigger_tokens = _tokenize(trigger)
            if not trigger_tokens:
                continue
            if trigger in task_lower:
                score += 2.0 * len(trigger_tokens)
                matched.append(trigger)
            else:
                overlap = trigger_tokens & task_tokens
                if overlap:
                    score += len(overlap) / len(trigger_tokens)
                    matched.append(trigger)
        if score >= min_score:
            matches.append(SkillMatch(skill=skill, score=score, matched_triggers=matched))
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:top_k]


def recommend(registry: SkillRegistry, task_description: str) -> SkillMatch | None:
    matches = find_skills(registry, task_description, top_k=1)
    return matches[0] if matches else None
