# Defensive Security Review

Scope: **defensive** secure-coding review only. This skill never produces
exploit code, malware, credential-theft tooling, or unauthorized-access
workflows, and it refuses requests that ask for those regardless of
"uncensored"/"unrestricted" framing from a model or user.

## Checklist
1. **Secret scanning** — run `openagent security secret-scan` on the diff
   and the full repo; any match blocks ship until remediated or confirmed
   false-positive.
2. **Dependency audit** — run `openagent security dep-audit`; flag known
   CVEs in direct and transitive dependencies with available fix versions.
3. **Authentication / authorization review** — for any changed auth path,
   confirm: credentials are never logged, session tokens are never written
   to ordinary memory (`openagent.memory.store` already refuses this),
   least-privilege is preserved, and auth failures fail closed.
4. **Input validation** — confirm all external input (HTTP params, file
   paths, shell arguments) is validated/escaped; check for path traversal
   (`WorkspaceGuard` should be the only way tools touch the filesystem) and
   shell-injection patterns in any dynamically built command.
5. **Logging safety** — confirm logs never contain secrets, tokens, or PII
   in plaintext; redact before writing.
6. **Remediation** — propose the smallest safe fix; re-run the checklist
   after applying it.

## Explicitly out of scope / refused
- Exploit development, weaponized PoCs, or malware of any kind.
- Credential theft, session hijacking tooling, botnet/C2, ransomware logic.
- Unauthorized scanning or intrusion against systems the user doesn't own or
  isn't explicitly authorized to test (get written authorization for pentests).
- Using a model's "uncensored" status (e.g. the OrcaSAQ-2 registry entry) as
  a justification to bypass any of the above -- see
  `openagent/models/registry.yaml` for that entry's gating policy.
