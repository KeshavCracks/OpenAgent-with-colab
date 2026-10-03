"""OpenAgent Harness command-line interface.

Design goal: every acceptance-gate capability in the README is reachable
from a single `openagent <command>` entrypoint, and every command is cheap
enough to run on a low-RAM local machine (no model weights are ever loaded
into this process).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from openagent import __version__
from openagent.agent.builtin_tools import build_default_tool_registry
from openagent.agent.scheduler import SchedulerStore, tick
from openagent.agent.session import SessionStore
from openagent.agent.trajectory import read_trajectory, summarize_trajectory, iter_tool_call_details
from openagent.config import Config, ensure_state_dirs
from openagent.memory.store import MemoryStore, SecretInMemoryError
from openagent.mcp.manager import MCPManager, MCPServerSpec
from openagent.models.checksum import sha256_file
from openagent.models.registry import load_registry
from openagent.security.dep_audit import run_dependency_audit
from openagent.security.secret_scan import scan_tree
from openagent.skills.finder import find_skills
from openagent.skills.registry import SkillRegistry
from openagent.tools.base import WorkspaceGuard


def _print_json(obj) -> None:
    def default(o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return str(o)
    print(json.dumps(obj, indent=2, default=default))


# --------------------------------------------------------------------------- sessions
def cmd_new(args) -> int:
    ensure_state_dirs()
    store = SessionStore(Path.home() / ".openagent" / "sessions")
    meta = store.create(workspace=str(Path(args.workspace).resolve()), mode=args.mode)
    _print_json(meta.to_dict())
    return 0


def cmd_sessions(args) -> int:
    store = SessionStore(Path.home() / ".openagent" / "sessions")
    _print_json([m.to_dict() for m in store.list()])
    return 0


def cmd_status(args) -> int:
    store = SessionStore(Path.home() / ".openagent" / "sessions")
    _print_json(store.load(args.session_id).to_dict())
    return 0


def cmd_stop(args) -> int:
    store = SessionStore(Path.home() / ".openagent" / "sessions")
    _print_json(store.stop(args.session_id).to_dict())
    return 0


def cmd_checkpoint(args) -> int:
    traj_dir = Path.home() / ".openagent" / "trajectories"
    path = traj_dir / f"{args.session_id}.jsonl"
    events = read_trajectory(path)
    _print_json({"session_id": args.session_id, "checkpoint_label": args.label,
                 "trajectory_events_so_far": len(events)})
    return 0


# --------------------------------------------------------------------------- models
def cmd_models_list(args) -> int:
    registry = load_registry()
    rows = []
    for m in registry.all():
        rows.append({
            "id": m.id, "status": m.status, "role": m.role,
            "gate_passed": m.gate_passed, "license": m.raw.get("license"),
        })
    _print_json({"default": registry.default_model_id, "models": rows})
    return 0


def cmd_models_show(args) -> int:
    registry = load_registry()
    _print_json(registry.get(args.model_id).to_dict())
    return 0


def cmd_models_verify(args) -> int:
    registry = load_registry()
    entry = registry.get(args.model_id)
    if not entry.sha256:
        print(f"Model '{args.model_id}' has no pinned sha256 in the registry.", file=sys.stderr)
        return 2
    actual = sha256_file(args.path)
    ok = actual.lower() == entry.sha256.lower()
    _print_json({"model_id": args.model_id, "expected_sha256": entry.sha256, "actual_sha256": actual, "ok": ok})
    return 0 if ok else 1


# --------------------------------------------------------------------------- providers
def cmd_providers_bootstrap(args) -> int:
    registry = load_registry()
    entry = registry.get(args.model_id)
    cfg = Config.load()
    out_dir = args.out_dir or f"./bootstrap_out/{args.provider}"
    if args.provider == "colab":
        from openagent.providers.colab import ColabDriver
        driver = ColabDriver(cfg.provider_limits("colab"))
    elif args.provider == "kaggle":
        from openagent.providers.kaggle import KaggleDriver
        driver = KaggleDriver(cfg.provider_limits("kaggle"))
    else:
        print(f"Unknown provider: {args.provider}", file=sys.stderr)
        return 2
    files = driver.generate_bootstrap(entry, out_dir)
    _print_json({"provider": args.provider, "model_id": args.model_id, "generated_files": files})
    return 0


# --------------------------------------------------------------------------- mcp
def cmd_mcp_list(args) -> int:
    guard = WorkspaceGuard(root=Path.cwd())
    registry = build_default_tool_registry(guard)
    manager = MCPManager(registry, guard)
    _print_json({"builtin_tools": [s["function"]["name"] for s in manager.builtin_tool_list()]})
    return 0


# --------------------------------------------------------------------------- skills
def cmd_skills_list(args) -> int:
    registry = SkillRegistry()
    _print_json(registry.catalog_summary())
    return 0


def cmd_skills_show(args) -> int:
    registry = SkillRegistry()
    skill = registry.get(args.name)
    print(skill.load_body())
    return 0


def cmd_skills_find(args) -> int:
    registry = SkillRegistry()
    matches = find_skills(registry, args.task, top_k=args.top_k)
    _print_json([{"name": m.skill.name, "score": m.score, "matched_triggers": m.matched_triggers}
                 for m in matches])
    return 0


# --------------------------------------------------------------------------- memory
def cmd_memory(args) -> int:
    store = MemoryStore(Path.home() / ".openagent" / "memory" / "memory.sqlite3")
    try:
        if args.action == "remember":
            rec = store.remember(args.scope, args.key, args.value, provenance="cli")
            _print_json(rec.to_dict())
        elif args.action == "recall":
            _print_json([r.to_dict() for r in store.recall(args.scope, args.key)])
        elif args.action == "search":
            _print_json([r.to_dict() for r in store.search(args.scope, args.query)])
        elif args.action == "forget":
            _print_json({"deleted": store.forget(args.record_id)})
    except SecretInMemoryError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    finally:
        store.close()
    return 0


# --------------------------------------------------------------------------- research
def cmd_research_doctor(args) -> int:
    from openagent.research.agent_reach import AgentReach
    from openagent.research.doctor import run_doctor

    reach = AgentReach()
    for ch in ("web_search", "rss", "github", "youtube_transcript", "docs_lookup"):
        reach.register_channel(ch, lambda q: [])
    statuses = run_doctor(reach, configured_api_keys={})
    _print_json([dataclasses.asdict(s) for s in statuses])
    return 0


# --------------------------------------------------------------------------- security
def cmd_security_secret_scan(args) -> int:
    findings = scan_tree(args.path)
    _print_json([dataclasses.asdict(f) for f in findings])
    return 1 if findings else 0


def cmd_security_dep_audit(args) -> int:
    result = run_dependency_audit(args.path, ecosystem=args.ecosystem)
    _print_json(dataclasses.asdict(result))
    return 0


# --------------------------------------------------------------------------- benchmark
def cmd_benchmark_run(args) -> int:
    from openagent.benchmark.tasks.default_suite import build_default_suite

    harness = build_default_suite()
    results = harness.run_all(model_id=args.model_id)
    _print_json(results)
    return 0 if all(r["passed"] for r in results) else 1


# --------------------------------------------------------------------------- schedule
def cmd_schedule_add(args) -> int:
    store = SchedulerStore(Path.home() / ".openagent" / "schedule.json")
    task = store.add(args.name, args.interval_seconds, args.action)
    _print_json(dataclasses.asdict(task))
    return 0


def cmd_schedule_list(args) -> int:
    store = SchedulerStore(Path.home() / ".openagent" / "schedule.json")
    _print_json([dataclasses.asdict(t) for t in store.list()])
    return 0


def cmd_schedule_tick(args) -> int:
    store = SchedulerStore(Path.home() / ".openagent" / "schedule.json")
    results = tick(store, runner=lambda t: {"ran": True, "action": t.action})
    _print_json(results)
    return 0


# --------------------------------------------------------------------------- trajectory
def cmd_trajectory_show(args) -> int:
    path = Path.home() / ".openagent" / "trajectories" / f"{args.session_id}.jsonl"
    events = read_trajectory(path)
    if args.tool_calls_only:
        _print_json(list(iter_tool_call_details(events)))
    else:
        _print_json(summarize_trajectory(events))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openagent", description="OpenAgent Harness CLI")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new", help="create a new session")
    p.add_argument("--workspace", default=".")
    p.add_argument("--mode", default="local-workspace-remote-inference",
                    choices=["local-workspace-remote-inference", "remote-workspace-remote-execution"])
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("sessions", help="list sessions")
    p.set_defaults(func=cmd_sessions)

    p = sub.add_parser("status", help="show session status")
    p.add_argument("session_id")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("stop", help="stop a session")
    p.add_argument("session_id")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("checkpoint", help="record a checkpoint")
    p.add_argument("session_id")
    p.add_argument("--label", default="manual")
    p.set_defaults(func=cmd_checkpoint)

    models = sub.add_parser("models", help="model registry commands").add_subparsers(dest="models_cmd", required=True)
    p = models.add_parser("list"); p.set_defaults(func=cmd_models_list)
    p = models.add_parser("show"); p.add_argument("model_id"); p.set_defaults(func=cmd_models_show)
    p = models.add_parser("verify"); p.add_argument("model_id"); p.add_argument("path"); p.set_defaults(func=cmd_models_verify)

    providers = sub.add_parser("providers", help="provider driver commands").add_subparsers(dest="providers_cmd", required=True)
    p = providers.add_parser("bootstrap")
    p.add_argument("provider", choices=["colab", "kaggle"])
    p.add_argument("model_id")
    p.add_argument("--out-dir", default=None)
    p.set_defaults(func=cmd_providers_bootstrap)

    mcp = sub.add_parser("mcp", help="MCP commands").add_subparsers(dest="mcp_cmd", required=True)
    p = mcp.add_parser("list"); p.set_defaults(func=cmd_mcp_list)

    skills = sub.add_parser("skills", help="skill registry/finder").add_subparsers(dest="skills_cmd", required=True)
    p = skills.add_parser("list"); p.set_defaults(func=cmd_skills_list)
    p = skills.add_parser("show"); p.add_argument("name"); p.set_defaults(func=cmd_skills_show)
    p = skills.add_parser("find"); p.add_argument("task"); p.add_argument("--top-k", type=int, default=3); p.set_defaults(func=cmd_skills_find)

    memory = sub.add_parser("memory", help="agent memory").add_subparsers(dest="memory_cmd", required=True)
    p = memory.add_parser("remember"); p.add_argument("scope"); p.add_argument("key"); p.add_argument("value")
    p.set_defaults(func=cmd_memory, action="remember")
    p = memory.add_parser("recall"); p.add_argument("scope"); p.add_argument("key", nargs="?")
    p.set_defaults(func=cmd_memory, action="recall")
    p = memory.add_parser("search"); p.add_argument("scope"); p.add_argument("query")
    p.set_defaults(func=cmd_memory, action="search")
    p = memory.add_parser("forget"); p.add_argument("record_id")
    p.set_defaults(func=cmd_memory, action="forget")

    research = sub.add_parser("research", help="research channels").add_subparsers(dest="research_cmd", required=True)
    p = research.add_parser("doctor"); p.set_defaults(func=cmd_research_doctor)

    security = sub.add_parser("security", help="defensive security tools").add_subparsers(dest="security_cmd", required=True)
    p = security.add_parser("secret-scan"); p.add_argument("path", default=".", nargs="?"); p.set_defaults(func=cmd_security_secret_scan)
    p = security.add_parser("dep-audit"); p.add_argument("path", default=".", nargs="?"); p.add_argument("--ecosystem", default="python")
    p.set_defaults(func=cmd_security_dep_audit)

    benchmark = sub.add_parser("benchmark", help="benchmark harness").add_subparsers(dest="benchmark_cmd", required=True)
    p = benchmark.add_parser("run"); p.add_argument("--model-id", default="unspecified"); p.set_defaults(func=cmd_benchmark_run)

    schedule = sub.add_parser("schedule", help="scheduled tasks").add_subparsers(dest="schedule_cmd", required=True)
    p = schedule.add_parser("add"); p.add_argument("name"); p.add_argument("interval_seconds", type=float); p.add_argument("action")
    p.set_defaults(func=cmd_schedule_add)
    p = schedule.add_parser("list"); p.set_defaults(func=cmd_schedule_list)
    p = schedule.add_parser("tick"); p.set_defaults(func=cmd_schedule_tick)

    trajectory = sub.add_parser("trajectory", help="trajectory inspection").add_subparsers(dest="trajectory_cmd", required=True)
    p = trajectory.add_parser("show"); p.add_argument("session_id"); p.add_argument("--tool-calls-only", action="store_true")
    p.set_defaults(func=cmd_trajectory_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
