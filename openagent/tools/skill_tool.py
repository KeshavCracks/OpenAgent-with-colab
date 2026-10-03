"""Agent-facing tool wrapping skill discovery with progressive disclosure."""
from __future__ import annotations

from openagent.skills.finder import find_skills
from openagent.skills.registry import SkillRegistry
from openagent.tools.base import Tool


class SkillTool(Tool):
    name = "skills"
    description = (
        "Discover and load harness skills. 'find' returns only lightweight "
        "summaries (progressive disclosure); 'load' returns the full "
        "instructions body for exactly one named skill."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["find", "load", "catalog"]},
            "task_description": {"type": "string"},
            "name": {"type": "string"},
            "top_k": {"type": "integer", "default": 3},
        },
        "required": ["action"],
    }
    permissions = ("fs:read",)

    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def run(self, action: str, task_description: str | None = None, name: str | None = None, top_k: int = 3):
        if action == "catalog":
            return {"skills": self.registry.catalog_summary()}
        if action == "find":
            if not task_description:
                raise ValueError("'task_description' is required for action=find")
            matches = find_skills(self.registry, task_description, top_k=top_k)
            return {
                "matches": [
                    {"name": m.skill.name, "score": m.score, "matched_triggers": m.matched_triggers,
                     "summary": m.skill.summary}
                    for m in matches
                ]
            }
        if action == "load":
            if not name:
                raise ValueError("'name' is required for action=load")
            skill = self.registry.get(name)
            return {"name": skill.name, "body": skill.load_body(), "context_budget_tokens": skill.context_budget_tokens}
        raise ValueError(f"Unknown action: {action}")
