from openagent.agent.context import ContextBudget, ContextManager, estimate_tokens


def test_estimate_tokens_grows_with_content():
    small = [{"role": "user", "content": "hi"}]
    large = [{"role": "user", "content": "x" * 4000}]
    assert estimate_tokens(large) > estimate_tokens(small)


def test_no_compaction_under_soft_limit():
    budget = ContextBudget(soft_limit_tokens=100000, hard_limit_tokens=200000)
    manager = ContextManager(budget)
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    assert manager.maybe_compact(messages) == messages


def test_compaction_triggers_over_soft_limit_and_keeps_recent_turns():
    budget = ContextBudget(soft_limit_tokens=50, hard_limit_tokens=500, keep_recent_turns=2)
    manager = ContextManager(budget)
    messages = [{"role": "system", "content": "system prompt"}]
    for i in range(20):
        messages.append({"role": "user", "content": f"message number {i} " + "filler " * 10})
        messages.append({"role": "assistant", "content": f"response {i} " + "filler " * 10})

    compacted = manager.maybe_compact(messages)
    assert len(compacted) < len(messages)
    # system message preserved
    assert compacted[0]["role"] == "system"
    # a summary message was injected
    assert any(m.get("_openagent_summary") for m in compacted)
    # the most recent turns are kept verbatim
    assert compacted[-1]["content"] == messages[-1]["content"]
    assert len(manager.summarization_events) == 1


def test_custom_summarizer_is_used():
    budget = ContextBudget(soft_limit_tokens=10, hard_limit_tokens=500, keep_recent_turns=1)
    calls = []

    def fake_summarizer(msgs):
        calls.append(len(msgs))
        return "CUSTOM SUMMARY"

    manager = ContextManager(budget, summarizer=fake_summarizer)
    messages = [{"role": "user", "content": "a" * 100}, {"role": "assistant", "content": "b" * 100},
                {"role": "user", "content": "c" * 100}]
    compacted = manager.maybe_compact(messages)
    assert any(m.get("content") == "CUSTOM SUMMARY" for m in compacted)
    assert calls
