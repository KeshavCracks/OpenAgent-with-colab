# Scientific / Research Assistant Skill

This harness implements the *direction* requested (a broad, 160+ area
research-assistant skill set spanning literature review, methods
reproduction, and benchmark comparison) as a small set of composable,
auditable sub-skills rather than a single opaque mega-skill, so each claim
stays traceable. No specific third-party "160+ skills" repository was
supplied by the user and none is invented here -- if you have a specific
upstream catalog to integrate, add it to `openagent/skills/catalog/` with
its own pinned revision and license, following this manifest's shape.

## Rules (non-negotiable)
1. **No fabricated citations.** Every citation must resolve to a source that
   was actually fetched/read in this session (via `agent-reach` research
   tools or a provided document) -- never a plausible-sounding title/DOI
   invented from pattern completion.
2. **No fabricated benchmark numbers.** Distinguish:
   - *vendor-reported*: taken from a vendor's own blog/model card, unverified.
   - *locally reproduced*: measured by this harness's own benchmark run
     (`openagent.benchmark.harness`), with the exact command and environment
     recorded.
3. **Reproducible methods.** State exact versions, seeds, hardware, and
   commands used, not just a narrative description.
4. **Uncertainty labeling.** If evidence is thin, conflicting, or the source
   is low-quality, say so plainly instead of presenting a confident answer.

## Workflow
1. Define the research question precisely (what would falsify the answer?).
2. Gather sources via the research module (`openagent.research.agent_reach`),
   respecting login-gated-platform and paywall/anti-bot restrictions.
3. Extract claims with citations attached at extraction time (not added
   after the fact from memory).
4. Cross-check at least two independent sources for load-bearing claims.
5. Write the summary with inline citations and an explicit confidence/
   uncertainty note per claim.
6. Store durable, reusable findings in `memory` (scope `project:<repo>` or
   `user`) with `provenance` set to the source citation.
