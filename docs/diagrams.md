# Diagram-as-Code

`openagent.diagram.diagram_tool` generates [Mermaid](https://mermaid.js.org/)
source — plain, diffable, version-controllable text, not opaque binary
images (the same philosophy Claude Code and similar harnesses use for
architecture/sequence/trace diagrams).

## Generators

| Function | Produces | Typical use |
|---|---|---|
| `architecture_to_mermaid(components, edges, title="")` | `flowchart LR` | System/module diagrams (see the one in the project README). |
| `sequence_to_mermaid(participants, messages)` | `sequenceDiagram` | Request/response flows between components. |
| `threat_model_to_mermaid(trust_zones, assets, threats)` | annotated flowchart | STRIDE-style threat modeling for the defensive-security-review skill. |
| `agent_trace_to_mermaid(events)` | `sequenceDiagram` | Renders a `TrajectoryEvent` list (user messages, tool calls, assistant replies) as a visual trace — handy for debugging a run without reading raw JSONL. |

```python
from openagent.diagram.diagram_tool import agent_trace_to_mermaid
from openagent.agent.trajectory import read_trajectory

events = read_trajectory("~/.openagent/trajectories/<session_id>.jsonl")
print(agent_trace_to_mermaid(events))
```

## Versioning convention

Check generated `.mmd` source into the repo next to whatever it documents
(e.g. `docs/diagrams/<name>.mmd`), not a rendered image, so diagram changes
show up as readable diffs in code review. GitHub, GitLab, and most Markdown
viewers render fenced ` ```mermaid ` blocks directly — no build step needed
to *view* a diagram.

## Optional rendering to SVG/PNG

Rendering is a separate, optional step: if you have
[`mermaid-cli`](https://github.com/mermaid-js/mermaid-cli) (`mmdc`)
installed locally, you can render any generated source yourself:

```bash
python -c "from openagent.diagram.diagram_tool import architecture_to_mermaid; \
print(architecture_to_mermaid(['CLI','Agent Loop','Tools'], [('CLI','Agent Loop'),('Agent Loop','Tools')]))" \
  > /tmp/diagram.mmd
mmdc -i /tmp/diagram.mmd -o /tmp/diagram.svg
```

The harness itself never shells out to `mmdc` automatically — diagram
generation stays pure-Python and dependency-free so it works on the
low-RAM local machine without installing Node/Chromium.
