import pytest

from openagent.browser.browser_use import ActionKind, ApprovalRequiredError, BrowserAction, BrowserSession
from openagent.research.agent_reach import AgentReach, ChannelUnavailableError, Citation
from openagent.research.doctor import run_doctor


def test_agent_reach_returns_citations():
    reach = AgentReach()
    reach.register_channel("docs", lambda q: [Citation(url="https://docs.example.com", title="Docs", snippet=q)])
    result = reach.query("docs", "how to configure X")
    assert len(result.citations) == 1
    assert result.citations[0].url.startswith("https://")


def test_agent_reach_blocks_login_gated_target_without_session():
    reach = AgentReach()
    reach.register_channel("social", lambda q: [])
    with pytest.raises(ChannelUnavailableError):
        reach.query("social", "latest posts", target_platform="instagram.com")


def test_agent_reach_allows_login_gated_target_with_registered_session():
    reach = AgentReach()
    reach.register_channel("social", lambda q: [Citation(url="https://linkedin.com/post/1", title="p", snippet="s")])
    reach.register_user_session("linkedin.com", object())
    result = reach.query("social", "latest posts", target_platform="linkedin.com")
    assert len(result.citations) == 1


def test_agent_reach_discards_login_gated_citation_without_session():
    reach = AgentReach()
    reach.register_channel("web", lambda q: [Citation(url="https://reddit.com/r/x", title="t", snippet="s")])
    with pytest.raises(ChannelUnavailableError):
        reach.query("web", "search reddit")


def test_doctor_reports_login_gated_platforms_unavailable_by_default():
    reach = AgentReach()
    statuses = run_doctor(reach)
    by_name = {s.name: s for s in statuses}
    assert by_name["instagram.com"].status == "unavailable"
    assert by_name["linkedin.com"].status == "unavailable"


def test_doctor_reports_configured_session_as_available():
    reach = AgentReach()
    reach.register_user_session("github.com", object())
    # github.com isn't in LOGIN_GATED_PLATFORMS so it won't appear here;
    # use a gated one with a registered session instead.
    reach.register_user_session("linkedin.com", object())
    statuses = run_doctor(reach)
    by_name = {s.name: s for s in statuses}
    assert by_name["linkedin.com"].status == "available"


def test_doctor_reports_missing_api_key_channel_unavailable():
    reach = AgentReach()
    reach.register_channel("youtube", lambda q: [])
    statuses = run_doctor(reach, configured_api_keys={"youtube": False})
    by_name = {s.name: s for s in statuses}
    assert by_name["youtube"].status == "unavailable"


def test_browser_blocks_sensitive_action_without_approval():
    session = BrowserSession(backend=lambda a: {"ok": True})
    with pytest.raises(ApprovalRequiredError):
        session.perform(BrowserAction(kind=ActionKind.PAYMENT, target="https://shop.example.com/checkout"))


def test_browser_allows_sensitive_action_with_approval_token():
    session = BrowserSession(backend=lambda a: {"ok": True})
    result = session.perform(BrowserAction(
        kind=ActionKind.UPLOAD, target="https://example.com/upload", approval_token="user-ok",
    ))
    assert result == {"ok": True}


def test_browser_allows_non_sensitive_action_without_approval():
    session = BrowserSession(backend=lambda a: {"title": "Example", "text": "hello"})
    result = session.perform(BrowserAction(kind=ActionKind.NAVIGATE, target="https://example.com"))
    assert result["title"] == "Example"
    assert len(session.citations) == 1
    assert session.citations[0].url == "https://example.com"


def test_browser_approver_callback_can_approve():
    approved = []

    def approver(action):
        approved.append(action.kind)
        return True

    session = BrowserSession(backend=lambda a: {"ok": True}, approver=approver)
    session.perform(BrowserAction(kind=ActionKind.LOGIN, target="https://example.com/login"))
    assert approved == [ActionKind.LOGIN]
