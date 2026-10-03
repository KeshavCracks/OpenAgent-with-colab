from openagent.skills.finder import find_skills, recommend
from openagent.skills.registry import SkillRegistry


def test_registry_loads_catalog():
    registry = SkillRegistry()
    names = registry.names()
    assert "lifecycle-spec-plan-build-ship" in names
    assert "defensive-security-review" in names
    assert "agent-reach-research" in names


def test_catalog_summary_is_lightweight():
    registry = SkillRegistry()
    summary = registry.catalog_summary()
    for s in summary:
        assert "body" not in s  # progressive disclosure: no full body in the summary
        assert s["context_budget_tokens"] < 2000


def test_load_body_returns_full_instructions():
    registry = SkillRegistry()
    skill = registry.get("defensive-security-review")
    body = skill.load_body()
    assert "secret scan" in body.lower() or "secret-scan" in body.lower()
    assert len(body) > len(skill.summary)


def test_finder_recommends_security_skill_for_security_task():
    registry = SkillRegistry()
    match = recommend(registry, "Please do a security review and scan for leaked secrets before I merge")
    assert match is not None
    assert match.skill.name == "defensive-security-review"


def test_finder_recommends_diagram_skill():
    registry = SkillRegistry()
    match = recommend(registry, "Can you draw an architecture diagram of this system?")
    assert match is not None
    assert match.skill.name == "diagram-as-code"


def test_finder_recommends_research_skill():
    registry = SkillRegistry()
    match = recommend(registry, "I need a literature review with citations on this topic")
    assert match is not None
    assert match.skill.name == "scientific-research-assistant"


def test_finder_recommends_browser_skill():
    registry = SkillRegistry()
    match = recommend(registry, "take a screenshot of the page and inspect the dom")
    assert match is not None
    assert match.skill.name == "browser-use-workflow"


def test_finder_returns_nothing_for_unrelated_task():
    registry = SkillRegistry()
    matches = find_skills(registry, "zzz qqq unrelated nonsense ppp", min_score=0.5)
    assert matches == []


def test_finder_respects_top_k():
    registry = SkillRegistry()
    matches = find_skills(registry, "security review and research citations and diagram", top_k=2)
    assert len(matches) <= 2
