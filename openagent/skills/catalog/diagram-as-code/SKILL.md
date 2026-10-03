# Diagram as Code

Diagrams are produced as version-controlled **source** (Mermaid or
Graphviz/DOT), using `openagent.diagram`, so they diff cleanly in code
review and are never an opaque binary blob.

## Supported diagram kinds
- `architecture` — components + dependencies (Mermaid `graph`/`flowchart`).
- `sequence` — request/response or agent/tool-call sequences (Mermaid
  `sequenceDiagram`).
- `dataflow` — data sources/sinks and transformations (Graphviz digraph).
- `threat-model` — STRIDE-style trust boundaries and threats (Mermaid
  flowchart with a threat-annotation convention, see
  `openagent/diagram/diagram_tool.py`).
- `agent-trace` — turns a trajectory JSONL file into a sequence diagram of
  model turns and tool calls (`openagent diagram from-trajectory`).

## Workflow
1. Generate or hand-write the `.mmd`/`.dot` source file into the workspace
   (never only an image).
2. Optionally render to SVG/PNG via `openagent diagram render` (requires the
   `mermaid-cli`/`graphviz` binaries locally -- the harness degrades
   gracefully to "source only" if they're not installed).
3. Commit the source file; treat the rendered image as a derived artifact.
