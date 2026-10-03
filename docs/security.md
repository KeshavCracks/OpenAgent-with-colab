# Security

## Secrets policy (hard rules, enforced in code)

1. **No API key, token, cookie, password, or other credential is ever
   committed** — not in `config/default.yaml`, not in bootstrap scripts, not
   in example files, not in tests. Real secrets live only in a local
   `.env` (gitignored; `.env.example` is the only committed template) or
   the OS keyring.
2. Checked-in config may only reference secrets as `env:VAR_NAME`,
   `keyring:service:key`, or the literal placeholder `CHANGE_ME` /
   `REPLACE_ME`. `openagent.config.resolve_secret()` is the only sanctioned
   way to turn a reference into a real value at runtime.
3. `openagent.config.validate_no_literal_secrets()` scans config text
   against a conservative set of "this looks like a real secret" patterns
   (HF tokens, OpenAI-style keys, GitHub tokens, AWS access keys, Slack
   tokens, PEM private keys, Kaggle tokens, and a generic
   `key/secret/token/password = "..."` assignment) and refuses to load the
   file if anything matches. False positives are cheap; leaked tokens are
   not.
4. `openagent.security.secret_scan` provides the same pattern set as a
   general-purpose tree scanner (`scan_tree`) used by the
   `defensive-security-review` skill and by `openagent security
   secret-scan` — run it over any directory before committing or shipping.
5. `openagent.memory.store.MemoryStore` independently refuses to persist
   anything that looks like a secret (`SecretInMemoryError`), so the
   `memory remember`/`memory` tool can't be used as a secret-storage
   side-channel even if a prompt tries to coax it into one.
6. The llama-server runtime always binds to loopback
   (`runtime.server.bind: 127.0.0.1`) and requires a bearer token
   (`runtime.auth.bearer_token: env:LLAMA_SERVER_TOKEN`); any tunnel into
   it is short-lived and authenticated (`runtime.tunnel.ttl_minutes`), never
   a long-lived public endpoint. MCP servers are refused outright if marked
   `public_endpoint=True` (`openagent.mcp.manager.MCPServerSpec`).

```bash
openagent security secret-scan .          # tree-wide secret scan (exit 1 if findings)
openagent security dep-audit . --ecosystem python   # wraps pip-audit / npm audit
```

## Defensive-only cybersecurity module

`openagent.security` (modeled on Anthropic's published cybersecurity-skills
guidance for *defensive* use) covers:

- **Secret scanning** (`secret_scan.py`) — see above.
- **Dependency auditing** (`dep_audit.py`) — shells out to `pip-audit` /
  `npm audit --json` when available; reports "tool not available" rather
  than silently skipping, so a missing auditor is visible in quality-gate
  output rather than a false "all clear."
- **Auth-code review** (`auth_review.py`) — flags hardcoded credential
  checks and logging of sensitive values in application code.

**Explicitly out of scope and never implemented here**: offensive
workflows, exploit development, intrusion/penetration tooling, malware,
or credential-theft techniques. The `defensive-security-review` skill
(`openagent/skills/catalog/defensive-security-review/skill.yaml`) states
this prohibition directly, and nothing in `openagent.security` accepts
"uncensored" framing as license to generate such content — see
[model-selection.md](model-selection.md#orcasaq2-cyber-27b-uncensored) for
how this applies to the gated community model specifically.

## Workspace containment

Every file/shell tool (`read`, `glob`, `grep`, `patch`, `shell`) is routed
through `openagent.tools.base.WorkspaceGuard`, which resolves paths against
a configured root and raises `WorkspaceViolationError` for:

- any path that resolves outside the workspace root, and
- any path matching a configured deny-list entry (`.git/config`,
  `.git/credentials`, `.env`, `.netrc` by default).

This applies uniformly whether the request came from the model, a skill,
or an MCP-exposed tool call.

## Research/browser safety

`openagent.research.agent_reach.AgentReach` raises `ChannelUnavailableError`
for any login-gated platform/URL without a registered, user-owned session —
there is no bypass code path. `openagent.browser.browser_use.BrowserSession`
raises `ApprovalRequiredError` for sensitive actions (login, upload,
payment, account action, destructive action) unless an explicit
`approval_token` or `approver` callback approves it. See
[research-skill-direction.md](research-skill-direction.md) and the project
README's module list for the full policy.

## Reporting a vulnerability

This is a reference/educational harness, not a hosted service. If you find
a security issue in the harness code itself (e.g. a workspace-containment
bypass), please open a GitHub issue describing the problem — do not include
real credentials, cookies, or exploit payloads targeting third-party
services in the report.
