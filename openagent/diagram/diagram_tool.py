"""Diagram-as-code generators (Mermaid source, version-controllable text).

Claude-Code-style: diagrams are checked-in `.mmd` source, not opaque images.
Rendering to SVG/PNG is a separate, optional step (see docs/diagrams.md) that
shells out to `mmdc` (mermaid-cli) if it's installed locally.
"""
from __future__ import annotations

import re

from openagent.agent.trajectory import TrajectoryEvent


def _safe_id(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", label)[:40] or "node"


def architecture_to_mermaid(components: list[str], edges: list[tuple[str, str]], title: str = "") -> str:
    lines = ["%%{init: {'theme': 'neutral'}}%%", "flowchart LR"]
    if title:
        lines.insert(1, f"  %% {title}")
    for c in components:
        lines.append(f"  {_safe_id(c)}[\"{c}\"]")
    for a, b in edges:
        lines.append(f"  {_safe_id(a)} --> {_safe_id(b)}")
    return "\n".join(lines) + "\n"


def sequence_to_mermaid(participants: list[str], messages: list[tuple[str, str, str]]) -> str:
    lines = ["sequenceDiagram"]
    for p in participants:
        lines.append(f"  participant {_safe_id(p)} as {p}")
    for src, dst, label in messages:
        lines.append(f"  {_safe_id(src)}->>{_safe_id(dst)}: {label}")
    return "\n".join(lines) + "\n"


def threat_model_to_mermaid(trust_boundaries: list[str], assets: list[str], threats: list[tuple[str, str, str]]) -> str:
    """`threats` is a list of (asset, STRIDE category, description)."""
    lines = ["flowchart TB"]
    for b in trust_boundaries:
        lines.append(f"  subgraph {_safe_id(b)}[\"{b}\"]")
        lines.append("  end")
    for a in assets:
        lines.append(f"  {_safe_id(a)}[(\"{a}\")]")
    for asset, category, desc in threats:
        tid = _safe_id(f"threat_{asset}_{category}")
        lines.append(f"  {tid}{{\"[{category}] {desc}\"}}")
        lines.append(f"  {tid} -.-> {_safe_id(asset)}")
    return "\n".join(lines) + "\n"


def agent_trace_to_mermaid(events: list[TrajectoryEvent], max_events: int = 60) -> str:
    """Turn a trajectory into a sequence diagram of model turns + tool calls."""
    lines = ["sequenceDiagram", "  participant User", "  participant Agent", "  participant Tools"]
    for e in events[:max_events]:
        if e.type == "message":
            role = e.data.get("role", "?")
            content = str(e.data.get("content", ""))[:60].replace("\n", " ")
            if role == "user":
                lines.append(f'  User->>Agent: {content}')
            elif role == "assistant":
                lines.append(f'  Agent-->>User: {content}')
        elif e.type == "tool_call":
            tool = e.data.get("tool", "?")
            ok = e.data.get("ok", True)
            lines.append(f'  Agent->>Tools: {tool}()')
            status = "ok" if ok else "error"
            lines.append(f'  Tools-->>Agent: {status}')
        elif e.type == "phase_switch":
            phase = e.data.get("phase", "?")
            lines.append(f'  Note over Agent: phase={phase}')
    return "\n".join(lines) + "\n"
