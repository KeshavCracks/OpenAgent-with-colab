# Examples

`sessions/example-session-001.json` and
`trajectories/example-session-001.jsonl` are a small, hand-built but
format-accurate example of what a real harness run produces, checked in so
you can see the trajectory/session shape without first running a live
session against a GPU backend. It depicts a plan → execute flow: read
`app.py`, patch in a `/health` route, run `pytest`, report back.

Inspect it with the real CLI tooling (no backend required — these are just
local files):

```bash
python -c "
from pathlib import Path
from openagent.agent.trajectory import read_trajectory, summarize_trajectory, iter_tool_call_details
import json
events = read_trajectory(Path('examples/trajectories/example-session-001.jsonl'))
print(json.dumps(summarize_trajectory(events), indent=2))
print(json.dumps(list(iter_tool_call_details(events)), indent=2))
"
```

Or render it as a diagram:

```bash
python -c "
from pathlib import Path
from openagent.agent.trajectory import read_trajectory
from openagent.diagram.diagram_tool import agent_trace_to_mermaid
events = read_trajectory(Path('examples/trajectories/example-session-001.jsonl'))
print(agent_trace_to_mermaid(events))
"
```

A real session's files live under `~/.openagent/sessions/` and
`~/.openagent/trajectories/` (see
[docs/session-lifecycle.md](../docs/session-lifecycle.md)) — these example
copies are just for documentation and are not read by the CLI by default.
