from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from orchestrator.config import AppConfig
from orchestrator.store import StateStore


def evaluate_run(
    store: StateStore,
    run_id: str,
    config: AppConfig | None = None,
) -> list[dict[str, Any]]:
    outputs = store.outputs(run_id)
    events = store.events(run_id)
    starts: dict[tuple[int, str], datetime] = {}
    completions: dict[tuple[int, str, str], dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []

    for event in events:
        payload = event["payload"]
        if event["kind"] == "stage.started":
            starts[(int(payload["round"]), str(payload["stage"]))] = datetime.fromisoformat(
                event["created_at"]
            )
        elif event["kind"] == "agent.completed":
            key = (
                int(payload["round"]),
                str(payload["stage"]),
                str(event["actor"]),
            )
            completions[key] = event
        elif event["kind"] == "route.failed":
            failures.append(event)

    accepted: set[str] = set()
    overridden_rounds: set[int] = set()
    for event in events:
        if event["kind"] == "decision.overridden":
            overridden_rounds.add(int(event["payload"]["round"]))
    for output in outputs:
        if output["persona"] != "judge" or not output.get("parsed"):
            continue
        accepted.update(str(item) for item in output["parsed"].get("accepted_claims") or ())

    rows = []
    completed_pairs: set[tuple[str, str]] = set()
    for output in outputs:
        parsed = output.get("parsed") or {}
        claims = parsed.get("claims") if isinstance(parsed.get("claims"), list) else []
        evidence = (
            parsed.get("evidence") if isinstance(parsed.get("evidence"), list) else []
        )
        claim_ids = {
            str(claim.get("id"))
            for claim in claims
            if isinstance(claim, dict) and claim.get("id") is not None
        }
        key = (output["round_number"], output["stage"], output["persona"])
        completion = completions.get(key)
        started = starts.get((output["round_number"], output["stage"]))
        duration = None
        composed_primary = output["model"]
        if completion:
            composed_primary = str(
                completion["payload"].get("composed_primary") or output["model"]
            )
            if started:
                duration = (
                    datetime.fromisoformat(completion["created_at"]) - started
                ).total_seconds()
        route_failures = [
            event
            for event in failures
            if event["actor"] == output["persona"]
            and (started is None or event["created_at"] >= started.isoformat())
            and event["created_at"] <= output["created_at"]
        ]
        own_route_failures = [
            event
            for event in route_failures
            if event["payload"].get("model") == output["model"]
        ]
        conflicts = _independence_conflicts(output, outputs, config)
        survived = len(claim_ids & accepted)
        recommendation = "retain" if survived else "evaluate"
        if output["persona"] == "judge":
            if output["round_number"] in overridden_rounds:
                recommendation = "recalibrate"
            else:
                recommendation = "retain" if parsed.get("decision") else "evaluate"
        if conflicts and recommendation == "retain":
            recommendation = "independent-recheck"
        rows.append(
            {
                "persona": output["persona"],
                "model": output["model"],
                "round": output["round_number"],
                "duration_seconds": duration,
                "claims": len(claims),
                "evidence": len(evidence),
                "accepted_claims": survived,
                "input_tokens": output["input_tokens"],
                "output_tokens": output["output_tokens"],
                "cache_tokens": output["cache_read_tokens"]
                + output["cache_write_tokens"],
                "estimated_cost_usd": output["estimated_cost_usd"],
                "fallback": output["model"] != composed_primary,
                "route_failures": len(own_route_failures),
                "fallback_failures": len(route_failures),
                "independence_conflicts": conflicts,
                "judge_overridden": output["round_number"] in overridden_rounds,
                "recommendation": recommendation,
            }
        )
        completed_pairs.add((output["persona"], output["model"]))

    failure_counts: dict[tuple[str, str], int] = defaultdict(int)
    for event in failures:
        failure_counts[(str(event["actor"]), str(event["payload"]["model"]))] += 1
    for (persona, model), count in failure_counts.items():
        if (persona, model) in completed_pairs:
            continue
        rows.append(
            {
                "persona": persona,
                "model": model,
                "round": None,
                "duration_seconds": None,
                "claims": 0,
                "evidence": 0,
                "accepted_claims": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_tokens": 0,
                "estimated_cost_usd": None,
                "fallback": False,
                "route_failures": count,
                "fallback_failures": count,
                "independence_conflicts": [],
                "judge_overridden": False,
                "recommendation": "demote",
            }
        )
    return rows


def _independence_conflicts(
    output: dict[str, Any],
    outputs: list[dict[str, Any]],
    config: AppConfig | None,
) -> list[str]:
    if config is None:
        return []
    persona = str(output["persona"])
    peers = []
    for left, right in config.team_policy.independence_pairs:
        if persona == left:
            peers.append(right)
        elif persona == right:
            peers.append(left)
    model = config.models[str(output["model"])]
    conflicts = []
    for peer in peers:
        candidates = [
            item
            for item in outputs
            if item["round_number"] == output["round_number"]
            and item["persona"] == peer
        ]
        if not candidates:
            continue
        peer_model = config.models[str(candidates[-1]["model"])]
        if peer_model.id == model.id or peer_model.family == model.family:
            conflicts.append(peer)
    return sorted(conflicts)
