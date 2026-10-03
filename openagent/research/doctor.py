"""Channel status checks, equivalent to `agent-reach doctor`."""
from __future__ import annotations

import dataclasses

from openagent.research.agent_reach import AgentReach, LOGIN_GATED_PLATFORMS


@dataclasses.dataclass
class ChannelStatus:
    name: str
    status: str  # "available" | "unavailable" | "degraded"
    detail: str = ""


def run_doctor(reach: AgentReach, configured_api_keys: dict[str, bool] | None = None) -> list[ChannelStatus]:
    """Report each registered channel's status plus the always-listed
    login-gated platforms (which are unavailable unless a user session was
    registered)."""
    configured_api_keys = configured_api_keys or {}
    results: list[ChannelStatus] = []

    for name in reach.available_channels():
        needs_key = name in configured_api_keys
        if needs_key and not configured_api_keys[name]:
            results.append(ChannelStatus(name, "unavailable", "required API key/credential not configured"))
        else:
            results.append(ChannelStatus(name, "available", "channel registered and ready"))

    for platform in sorted(LOGIN_GATED_PLATFORMS):
        if platform in reach._user_sessions:  # noqa: SLF001 - doctor is allowed to introspect
            results.append(ChannelStatus(platform, "available", "user-owned session configured"))
        else:
            results.append(ChannelStatus(
                platform, "unavailable",
                "login-gated platform; requires an explicit user-owned session/cookie/integration",
            ))
    return results
