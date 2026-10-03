from openagent.context_system.viking import ContextItem, ContextSource, OpenVikingContext


def test_ranks_by_relevance():
    viking = OpenVikingContext(max_context_tokens=10000)
    viking.register_source(ContextSource(
        name="repo",
        fetch=lambda q: [
            ContextItem(source="repo", identifier="a.py", content="def login(user, password): pass",
                        provenance="repo:a.py"),
            ContextItem(source="repo", identifier="b.py", content="def add(a, b): return a + b",
                        provenance="repo:b.py"),
        ],
    ))
    items = viking.query("how does login work")
    assert items[0].identifier == "a.py"


def test_redacts_secret_like_content():
    viking = OpenVikingContext(max_context_tokens=10000)
    viking.register_source(ContextSource(
        name="repo",
        fetch=lambda q: [ContextItem(source="repo", identifier="config.py",
                                      content='API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"',
                                      provenance="repo:config.py")],
    ))
    items = viking.query("api key")
    assert items[0].redacted is True
    assert "sk-abc" not in items[0].content


def test_respects_context_budget():
    viking = OpenVikingContext(max_context_tokens=5)  # tiny budget
    viking.register_source(ContextSource(
        name="repo",
        fetch=lambda q: [ContextItem(source="repo", identifier=f"f{i}.py", content="x" * 200, provenance="repo")
                          for i in range(20)],
    ))
    items = viking.query("x", top_k=20)
    report = viking.budget_report(items)
    assert report["tokens_used"] <= 5


def test_disabled_source_is_skipped():
    viking = OpenVikingContext()
    viking.register_source(ContextSource(
        name="issues", fetch=lambda q: [ContextItem(source="issues", identifier="1", content="bug report",
                                                      provenance="issue:1")],
        enabled=False,
    ))
    items = viking.query("bug")
    assert items == []


def test_query_can_restrict_to_named_sources():
    viking = OpenVikingContext()
    viking.register_source(ContextSource(name="repo", fetch=lambda q: [
        ContextItem(source="repo", identifier="r1", content="repo content about auth", provenance="repo")]))
    viking.register_source(ContextSource(name="memory", fetch=lambda q: [
        ContextItem(source="memory", identifier="m1", content="memory content about auth", provenance="memory")]))
    items = viking.query("auth", source_names=["memory"])
    assert len(items) == 1
    assert items[0].source == "memory"
