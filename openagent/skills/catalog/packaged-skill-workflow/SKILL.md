# Packaged SKILL.md workflow

Adapted from the packaging/discovery approach in
[vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills)
(pinned at `063bee94`). GitHub's API reported no detected LICENSE file for
this repo as of 2026-10-03 -- treat any verbatim content from it as
"all rights reserved by default" until you've manually confirmed otherwise;
this harness only reimplements the *pattern* (manifest + body file +
discovery), not vendored source.

## Pattern
- A "packaged skill" is a directory with:
  - `skill.yaml` (or `SKILL.md` frontmatter in the original project) — the
    small, always-visible manifest: name, version, triggers, required
    tools/permissions, context budget.
  - A body file (`SKILL.md` here) with the full instructions, loaded only
    when the skill is selected (progressive disclosure).
- `openagent skills list` shows the manifest summaries only.
- `openagent skills show <name>` loads the body file on demand.
- `openagent skills find "<task description>"` runs the skill-finder
  (`openagent.skills.finder`) to recommend the best match(es).

## Adding a new packaged skill
1. Create `openagent/skills/catalog/<name>/skill.yaml` with the required
   fields (see `openagent/skills/registry.py::SkillManifest`).
2. Add a `SKILL.md` body with the actual instructions.
3. Add triggers that are specific enough to avoid false-positive matches on
   unrelated tasks.
4. Add a test case to `tests/test_skills.py` asserting the finder recommends
   this skill for a representative task description.
