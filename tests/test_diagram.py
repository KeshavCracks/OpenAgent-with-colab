from openagent.agent.trajectory import TrajectoryEvent
from openagent.diagram.diagram_tool import (
    agent_trace_to_mermaid,
    architecture_to_mermaid,
    sequence_to_mermaid,
    threat_model_to_mermaid,
)


def test_architecture_diagram_contains_nodes_and_edges():
    src = architecture_to_mermaid(["CLI", "Agent Loop", "Tool Registry"],
                                   [("CLI", "Agent Loop"), ("Agent Loop", "Tool Registry")])
    assert "flowchart" in src
    assert "CLI" in src
    assert "-->" in src


def test_sequence_diagram():
    src = sequence_to_mermaid(["User", "Agent"], [("User", "Agent", "ask question")])
    assert "sequenceDiagram" in src
    assert "ask question" in src


def test_threat_model_diagram():
    src = threat_model_to_mermaid(["Internet", "Internal"], ["API", "DB"],
                                   [("API", "Spoofing", "unauthenticated endpoint")])
    assert "Spoofing" in src
    assert "API" in src


def test_agent_trace_diagram_from_trajectory_events():
    events = [
        TrajectoryEvent(event_id="1", session_id="s", type="message", t=0.0,
                         data={"role": "user", "content": "do the thing"}),
        TrajectoryEvent(event_id="2", session_id="s", type="tool_call", t=1.0,
                         data={"tool": "shell", "ok": True}),
        TrajectoryEvent(event_id="3", session_id="s", type="message", t=2.0,
                         data={"role": "assistant", "content": "done"}),
    ]
    src = agent_trace_to_mermaid(events)
    assert "sequenceDiagram" in src
    assert "shell()" in src
    assert "do the thing" in src
