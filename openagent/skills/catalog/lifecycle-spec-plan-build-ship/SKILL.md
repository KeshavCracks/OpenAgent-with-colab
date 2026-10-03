# Spec -> Plan -> Build -> Test -> Review -> Ship

Adapted from the workflow lifecycle in
[addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
(MIT, pinned at `9d0c60d4`). Only this body is loaded once the skill is
selected -- the catalog summary shown to every prompt is a single line.

## Personas
- **Spec writer** — turns a request into an explicit, falsifiable spec:
  inputs, outputs, edge cases, non-goals.
- **Planner** — breaks the spec into ordered, independently-verifiable steps.
- **Builder** — implements one step at a time using `patch` (never freehand
  file overwrites for existing files) and `shell` for builds/tests.
- **Reviewer** — a distinct pass (can be a different model/role, see
  `openagent.runtime.router`) that checks the diff against the spec, not
  just "does it run".
- **Security reviewer** — runs the defensive-security-review skill for any
  change touching auth, input parsing, secrets, or logging.

## Phases
1. **Spec**: write the spec into `todo` as a checklist; store durable
   decisions in `memory` (scope: `project:<repo>`), never secrets.
2. **Plan**: order the checklist by dependency; identify the smallest
   verifiable slice to build first.
3. **Build**: implement via `patch`; keep diffs small and reviewable.
4. **Test**: run the project's test suite with `shell` under a bounded
   timeout; capture full stdout/stderr into the trajectory.
5. **Review**: diff the change against the spec; run quality gates.
6. **Ship**: summarize verification evidence (test output, diff stats,
   security review result) before declaring the task done.

## Quality gates (must all pass before "ship")
- Tests pass (exit code 0, captured in the trajectory).
- Patch applied cleanly (the `patch` tool's context-validation already
  guarantees this at apply time).
- Security review completed for sensitive changes.
- No secrets introduced (run `openagent security secret-scan`).

## Verification evidence
Never assert "this works" without attaching the command and its output. The
trajectory recorder captures every tool call automatically -- reference the
relevant `tool_call` event ids in the final summary.
