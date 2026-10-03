# Browser Use Workflow

Wraps a real browser automation backend (see `openagent.browser.browser_use`,
designed against the [Browser Use](https://github.com/browser-use/browser-use)
project's capability set: navigate, click, fill forms, screenshot, inspect
DOM/console/network) behind an approval gate.

## Approval gate (hard requirement)
Before any of the following actions execute, the harness must have a
recorded approval event for *this specific action* in the trajectory:
- Logging in / submitting credentials.
- Uploading a file.
- Any payment or purchase flow.
- Any account-level action (delete, change settings, post publicly).
- Any other destructive operation (irreversible delete, send, publish).

`openagent.browser.browser_use.BrowserSession.perform()` raises
`ApprovalRequiredError` for these action kinds unless an approval token is
supplied -- there is no silent bypass path.

## Citations
Every claim sourced from a browsed page must record: URL, page title,
timestamp visited, and the exact text/selector used as evidence, so the
final answer can cite precisely what was read.

## Hard constraints
- Never bypass logins, paywalls, API restrictions, CAPTCHAs, anti-bot
  controls, copyright controls, or platform access rules.
- For login-gated platforms (Instagram, Facebook, Reddit, X/Twitter,
  Xiaohongshu, LinkedIn, etc.) only proceed with a user-owned, already
  authenticated browser session/cookie export -- never attempt to acquire
  or bypass credentials on the user's behalf.
- Prefer a dedicated test/secondary account where platform automation
  creates account risk.
