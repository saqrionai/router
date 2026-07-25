from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from orchestrator import __version__
from orchestrator.composer import TeamComposer
from orchestrator.config import AppConfig
from orchestrator.evaluation import evaluate_run
from orchestrator.fugu_router import FuguRouter
from orchestrator.reporting import render_bundle, write_artifacts, write_bundle
from orchestrator.store import StateStore


def default_state_path() -> Path:
    state_root = os.environ.get("ORCHESTRATOR_STATE_DIR")
    if state_root:
        return Path(state_root).expanduser() / "orchestrator.db"
    return Path.home() / ".local" / "state" / "orchestrator" / "orchestrator.db"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="orch",
        description="Durable multi-model research orchestration",
    )
    result.add_argument("--version", action="version", version=__version__)
    result.add_argument("--root", type=Path, help="orchestrator project root")
    result.add_argument("--state", type=Path, default=default_state_path())
    commands = result.add_subparsers(dest="command", required=True)

    show = commands.add_parser("show", help="show an archived legacy run")
    show.add_argument("run_id")
    show.add_argument("--json", action="store_true")

    commands.add_parser("runs", help="list recent runs")

    usage = commands.add_parser("usage", help="show direct token and cost usage")
    usage.add_argument("run_id", nargs="?")

    bundle = commands.add_parser("bundle", help="export model-agnostic context")
    bundle.add_argument("run_id")
    bundle.add_argument("--output", type=Path)

    artifacts = commands.add_parser(
        "artifacts", help="export durable artifacts from a run"
    )
    artifacts.add_argument("run_id")
    artifacts.add_argument("--output", type=Path)

    evaluate = commands.add_parser("eval", help="score model/persona results for a run")
    evaluate.add_argument("run_id")
    evaluate.add_argument("--json", action="store_true")

    commands.add_parser("models", help="list native-workflow worker routes")
    commands.add_parser("personas", help="list configured personas")
    team = commands.add_parser("team", help="compose and explain a mixed-model team")
    team.add_argument("--workflow", default="security-research-forum")
    team.add_argument("--task", default="")
    team.add_argument("--json", action="store_true")
    route = commands.add_parser(
        "route", help="show Fugu-style model probabilities for one persona"
    )
    route.add_argument("persona")
    route.add_argument("--task", default="")
    route.add_argument(
        "--model",
        action="append",
        dest="models",
        help="limit the worker pool; repeat for multiple routes",
    )
    route.add_argument("--json", action="store_true")
    commands.add_parser("doctor", help="check native-workflow routing support")
    return result


def _print_usage(rows: list[dict[str, object]]) -> None:
    if not rows:
        print("No usage recorded.")
        return
    print(
        f"{'PERSONA':14} {'MODEL':20} {'CALLS':>5} {'INPUT':>10} "
        f"{'OUTPUT':>10} {'CACHE':>10} {'COST':>10}"
    )
    for row in rows:
        cache = int(row["cache_read_tokens"]) + int(row["cache_write_tokens"])
        print(
            f"{str(row['persona']):14.14} {str(row['model']):20.20} "
            f"{int(row['calls']):5d} {int(row['input_tokens']):10d} "
            f"{int(row['output_tokens']):10d} {cache:10d} "
            f"${float(row['estimated_cost_usd']):9.4f}"
        )


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    config = AppConfig.load(args.root)
    store = StateStore(args.state)

    if args.command == "show":
        payload = {
            "run": store.run(args.run_id),
            "events": store.events(args.run_id),
            "messages": store.messages(args.run_id),
            "artifacts": store.artifacts(args.run_id),
            "checks": store.checks(args.run_id),
            "usage": store.usage_summary(args.run_id),
        }
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(render_bundle(store, args.run_id))
    elif args.command == "runs":
        for run in store.list_runs():
            task = run["task"].replace("\n", " ")[:72]
            print(
                f"{run['id']}  {run['status']:15} r{run['current_round']}  "
                f"{run['decision'] or '-':12} {task}"
            )
    elif args.command == "usage":
        _print_usage(store.usage_summary(args.run_id))
    elif args.command == "bundle":
        output = args.output or (
            args.state.parent / "bundles" / f"{args.run_id}.md"
        )
        print(write_bundle(store, args.run_id, output))
    elif args.command == "artifacts":
        output = args.output or (args.state.parent / "artifacts" / args.run_id)
        paths = write_artifacts(store, args.run_id, output)
        if not paths:
            print("No artifacts recorded.")
        for path in paths:
            print(path)
    elif args.command == "eval":
        rows = evaluate_run(store, args.run_id, config)
        if args.json:
            print(json.dumps(rows, indent=2, default=str))
        else:
            print(
                f"{'PERSONA':14} {'MODEL':20} {'SEC':>7} {'CLAIMS':>6} "
                f"{'EVID':>5} {'KEPT':>5} {'FAIL':>4} {'CORR':>4} "
                f"{'TOKENS':>10} ACTION"
            )
            for row in rows:
                duration = (
                    f"{float(row['duration_seconds']):.0f}"
                    if row["duration_seconds"] is not None
                    else "-"
                )
                tokens = int(row["input_tokens"]) + int(row["output_tokens"])
                conflicts = len(row["independence_conflicts"])
                print(
                    f"{str(row['persona']):14.14} {str(row['model']):20.20} "
                    f"{duration:>7} {int(row['claims']):6d} {int(row['evidence']):5d} "
                    f"{int(row['accepted_claims']):5d} {int(row['route_failures']):4d} "
                    f"{conflicts:4d} "
                    f"{tokens:10d} {row['recommendation']}"
                )
    elif args.command == "models":
        for route in config.models.values():
            mode = "recovery" if route.fallback_only else "primary"
            print(
                f"{route.id:20} {route.backend:12} {route.context_window:>9,}  "
                f"{route.family:10} {mode:8} {', '.join(route.styles)}"
            )
    elif args.command == "personas":
        for persona in config.personas.values():
            print(
                f"{persona.id:14} {persona.title:34} -> "
                f"{', '.join(persona.preferred_models)}"
            )
    elif args.command == "team":
        plan = TeamComposer(
            models=config.models,
            personas=config.personas,
            policy=config.team_policy,
        ).compose(config.workflow(args.workflow), args.task)
        payload = {
            "total_score": plan.total_score,
            "unique_models": plan.unique_models,
            "unique_families": plan.unique_families,
            "task_traits": plan.task_traits,
            "assignments": [
                {
                    "persona": assignment.persona,
                    "model": assignment.model,
                    "family": config.models[assignment.model].family,
                    "styles": config.models[assignment.model].styles,
                    "score": assignment.score,
                    "reasons": assignment.reasons,
                    "fallback_order": assignment.fallback_order,
                }
                for assignment in plan.assignments
            ],
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"team score={plan.total_score:.3f} "
                f"diversity={plan.unique_models} models/{plan.unique_families} families"
            )
            if plan.task_traits:
                print(
                    "task traits: "
                    + ", ".join(
                        f"{name}={value:.2f}"
                        for name, value in plan.task_traits.items()
                    )
                )
            for assignment in plan.assignments:
                model = config.models[assignment.model]
                print(
                    f"{assignment.persona:14} -> {assignment.model:20} "
                    f"[{model.family}] score={assignment.score:.3f}"
                )
                print(f"  {', '.join(assignment.reasons)}")
    elif args.command == "route":
        if args.persona not in config.personas:
            raise SystemExit(f"unknown persona: {args.persona}")
        model_ids = tuple(args.models or config.personas[args.persona].preferred_models)
        primary_model_ids = tuple(
            model_id
            for model_id in model_ids
            if not config.models[model_id].fallback_only
        )
        recovery_model_ids = tuple(
            model_id
            for model_id in model_ids
            if config.models[model_id].fallback_only
        )
        candidates = FuguRouter(
            models=config.models,
            personas=config.personas,
            policy=config.team_policy,
            outcomes=store.routing_outcomes(),
            observations=store.routing_observations(),
        ).rank(
            task=args.task,
            persona_id=args.persona,
            model_ids=primary_model_ids,
        )
        payload = {
            "persona": args.persona,
            "task": args.task,
            "routes": [candidate.as_dict() for candidate in candidates],
            "recovery_routes": list(recovery_model_ids),
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"persona={args.persona} pool={len(candidates)}")
            for candidate in candidates:
                print(
                    f"{candidate.model:22} p={candidate.probability:0.3f} "
                    f"score={candidate.score:0.3f} prior={candidate.prior_score:0.3f} "
                    f"terminal={candidate.terminal_success:0.3f} "
                    f"context={candidate.contextual_success:0.3f}/"
                    f"{candidate.contextual_observations} "
                    f"format={candidate.format_success:0.3f} calls={candidate.calls}"
                )
            if recovery_model_ids:
                print(f"recovery-only: {', '.join(recovery_model_ids)}")
    elif args.command == "doctor":
        print(f"config: ok ({len(config.models)} models, {len(config.personas)} personas)")
        print(f"state:  ok ({store.path})")
        for command in ("claude", "codex"):
            location = shutil.which(command)
            print(f"{command:10} {'ok ' + location if location else 'missing'}")
        wrapper = shutil.which("codex-subagent")
        print(f"{'codex-subagent':14} {'ok ' + wrapper if wrapper else 'missing'}")
        print("scheduler: claude-native-workflows only")

if __name__ == "__main__":
    main()
