# Scientific / Research Skill Direction

`openagent/skills/catalog/scientific-research-assistant/skill.yaml` is
**harness-authored** (not vendored from a specific external "Scientific
Agent Skills" repository — no such single authoritative, user-supplied URL
was given for this capability, and per project policy this harness does
not invent repository URLs for capability areas it wasn't pointed at).
Instead, the skill encodes a direction note distilled from the broadly
published, reputable guidance on agentic scientific/research workflows:
citations, reproducibility, and uncertainty are first-class requirements,
not a model nice-to-have.

## Why "160+ skill areas" is mentioned

The research-assistant space spans well over a hundred distinct task
shapes in practice — literature review, paper summarization, benchmark
reproduction, methods critique, dataset provenance checks, statistical
sanity checks, and so on. Rather than hand-author 160+ narrow skill
entries up front (which would bloat the catalog's context budget for no
real benefit), this harness ships **one** generically-triggered skill with
a strict policy and lets the finder/agent compose it with the other
built-in tools (`memory`, `read`, `grep`) per task. If a genuinely distinct
sub-skill earns its own triggers, verification procedure, and context
budget later, split it out as its own catalog entry at that point — see
`openagent.skills.registry.SkillRegistry` and
`openagent.skills.finder.find_skills` for how new entries are picked up
automatically (any `*/skill.yaml` under the catalog directory).

## Hard policy baked into the skill

From `scientific-research-assistant/skill.yaml`:

- Every factual claim must carry an inline citation resolvable to a real,
  fetchable source.
- Benchmark numbers must be explicitly labeled "vendor-reported" vs.
  "locally reproduced" — never presented as equivalent.
- Uncertainty must be stated explicitly whenever evidence is incomplete or
  conflicting.
- **Never fabricate** citations, papers, benchmark numbers, or
  experimental results. If a source can't be found or a number can't be
  reproduced locally, say so — don't invent a plausible-looking
  substitute.

This mirrors the same "never invent a URL/number" discipline applied
elsewhere in the harness (model registry entries, skill catalog sources,
and this documentation itself only ever cite sources that were actually
looked up).

## Relationship to Agent-Reach

This skill is the usual pairing for `openagent.research.agent_reach` —
research tasks typically need both the *policy* (no fabrication, cite
everything) and the *mechanism* (lawful search/RSS/GitHub/YouTube/docs
lookup, with login-gated platforms blocked unless a user-owned session is
registered). See `agent-reach-research` in the skill catalog and
[security.md](security.md#researchbrowser-safety).
