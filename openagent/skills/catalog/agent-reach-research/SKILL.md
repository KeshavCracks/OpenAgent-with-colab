# Agent-Reach Research Channels

Wraps lawful public research channels modeled after
[Panniantong/agent-reach](https://github.com/Panniantong/agent-reach) (MIT,
pinned at `a19a171f`): web search, RSS, GitHub, YouTube transcripts/search,
and general documentation lookup.

## Channel status ("doctor")
Run `openagent research doctor` (implemented in
`openagent.research.doctor`) before relying on any channel. Each channel
reports one of:
- `available` — reachable and authorized for the configured use.
- `unavailable` — not configured, rate-limited, or requires a login-gated
  session the user hasn't provided.
- `degraded` — reachable but failing some health checks (e.g. slow, partial
  results).

## Login-gated platforms
Instagram, Facebook, Reddit, X/Twitter, Xiaohongshu, LinkedIn, and similar
platforms are **always** `unavailable` unless the user has explicitly
configured their own authorized session (exported cookies stored locally
with restrictive file permissions, an official API token, or an authorized
integration). The harness never attempts to acquire, guess, or bypass
credentials, CAPTCHAs, or anti-bot measures to reach these platforms.

## Secondary accounts
Where a platform's automation terms create account risk (rate limits,
ban risk for bot-like behavior), prefer a dedicated test/secondary account
over the user's primary one.

## Credential hygiene
Cookies/tokens for research channels are stored locally only, with
restrictive permissions (0600), are never logged, and are never sent
anywhere except the originating platform's own endpoints.
