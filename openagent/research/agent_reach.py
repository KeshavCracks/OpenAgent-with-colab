"""Agent-Reach-style lawful public research channels.

Modeled on github.com/Panniantong/agent-reach's channel set (web search,
RSS, GitHub, YouTube transcripts/search, documentation lookup). Channel
implementations are injectable so the harness can be tested offline and so
a real Agent-Reach install can be wired in without touching callers.

Hard constraints enforced here, not just documented:
  * Login-gated platforms (Instagram, Facebook, Reddit, X/Twitter,
    Xiaohongshu, LinkedIn, ...) always come back `unavailable` unless the
    caller supplies an explicit, user-owned session object -- there is no
    code path that attempts to log in, solve a CAPTCHA, or otherwise bypass
    access controls.
  * Every result carries a Citation (url + fetched_at) -- nothing is
    returned as prose without a traceable source.
"""
from __future__ import annotations

import dataclasses
import time
from typing import Callable, Optional

LOGIN_GATED_PLATFORMS = {
    "instagram.com", "facebook.com", "reddit.com", "x.com", "twitter.com",
    "xiaohongshu.com", "linkedin.com",
}


class ChannelUnavailableError(RuntimeError):
    pass


@dataclasses.dataclass
class Citation:
    url: str
    title: str
    snippet: str
    fetched_at: float = dataclasses.field(default_factory=time.time)


@dataclasses.dataclass
class ResearchResult:
    channel: str
    query: str
    citations: list[Citation]


ChannelFn = Callable[[str], list[Citation]]


def _is_login_gated(url_or_platform: str) -> bool:
    lowered = url_or_platform.lower()
    return any(domain in lowered for domain in LOGIN_GATED_PLATFORMS)


class AgentReach:
    """Registry of research channels with login-gating enforcement."""

    def __init__(self):
        self._channels: dict[str, ChannelFn] = {}
        self._user_sessions: dict[str, object] = {}  # platform -> opaque user-owned session

    def register_channel(self, name: str, fn: ChannelFn) -> None:
        self._channels[name] = fn

    def register_user_session(self, platform: str, session: object) -> None:
        """Register a user-owned, already-authenticated session/cookie export
        for a login-gated platform. The harness never creates these itself."""
        self._user_sessions[platform.lower()] = session

    def available_channels(self) -> list[str]:
        return list(self._channels.keys())

    def _has_session_for_url(self, url: str) -> bool:
        lowered = url.lower()
        return any(platform in lowered for platform in self._user_sessions)

    def query(self, channel: str, query_text: str, target_platform: Optional[str] = None) -> ResearchResult:
        if target_platform and _is_login_gated(target_platform) and target_platform.lower() not in self._user_sessions:
            raise ChannelUnavailableError(
                f"'{target_platform}' is a login-gated platform with no user-owned session configured; "
                "marking unavailable rather than attempting a bypass."
            )
        if channel not in self._channels:
            raise ChannelUnavailableError(f"Unknown or unconfigured research channel: {channel}")
        citations = self._channels[channel](query_text)
        for c in citations:
            if _is_login_gated(c.url) and not self._has_session_for_url(c.url):
                raise ChannelUnavailableError(
                    f"Channel '{channel}' returned a login-gated URL ({c.url}) without an "
                    "authorized user session -- discarding rather than using it."
                )
        return ResearchResult(channel=channel, query=query_text, citations=citations)
