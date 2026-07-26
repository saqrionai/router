from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, TextIO

from orchestrator.beads import BeadsBridge, BeadsError
from orchestrator.cli import default_state_path
from orchestrator.composer import TeamComposer
from orchestrator.config import AppConfig
from orchestrator.fugu_router import FuguRouter
from orchestrator.eligibility import is_route_eligible
from orchestrator.store import StateStore


MODEL_AGENT_TYPES = {
    "anthropic": "orchestrator:opus-worker",
    "openai": "orchestrator:codex-worker",
}


class FuguMcpServer:
    """Small stdio MCP surface for Claude-native workflow routing."""

    def __init__(self, config: AppConfig, store: StateStore):
        self.config = config
        self.store = store
        self.beads = BeadsBridge()

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return self._result(
                request_id,
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": "orchestrator-fugu",
                        "version": "0.2.0",
                    },
                },
            )
        if method == "ping":
            return self._result(request_id, {})
        if method == "tools/list":
            return self._result(request_id, {"tools": self.tools()})
        if method == "tools/call":
            params = request.get("params")
            if not isinstance(params, dict):
                return self._error(request_id, -32602, "params must be an object")
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                return self._error(request_id, -32602, "arguments must be an object")
            try:
                value = self.call_tool(str(name), arguments)
            except (BeadsError, KeyError, TypeError, ValueError) as exc:
                return self._tool_result({"error": str(exc)}, is_error=True, request_id=request_id)
            return self._tool_result(value, request_id=request_id)
        return self._error(request_id, -32601, f"unknown method: {method}")

    @staticmethod
    def tools() -> list[dict[str, Any]]:
        return [
            {
                "name": "route_team",
                "description": (
                    "Compose a Fugu model/persona plan for a Claude native workflow. "
                    "Call this before launching an orchestrator workflow."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": ["task"],
                    "properties": {
                        "task": {"type": "string", "minLength": 1},
                        "workflow": {
                            "type": "string",
                            "default": "security-research-forum",
                        },
                    },
                },
            },
            {
                "name": "route_persona",
                "description": (
                    "Return learned Fugu route probabilities for one persona and task."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": ["task", "persona"],
                    "properties": {
                        "task": {"type": "string"},
                        "persona": {"type": "string"},
                    },
                },
            },
            {
                "name": "inspect_frontier",
                "description": (
                    "Return a bounded deterministic view of in-progress and "
                    "dependency-ready Beads without claiming or mutating work."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": ["workspace"],
                    "properties": {
                        "workspace": {"type": "string", "minLength": 1},
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 16,
                            "default": 8,
                        },
                    },
                },
            },
            {
                "name": "prepare_bead",
                "description": (
                    "Automatically resume the highest-priority in-progress Bead, "
                    "otherwise claim the highest-priority dependency-ready Bead, "
                    "or create one when no candidate exists. An explicit issue ID "
                    "overrides selection. This records durable project state but "
                    "never launches a model or scheduler."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": ["workspace", "task"],
                    "properties": {
                        "workspace": {"type": "string", "minLength": 1},
                        "task": {"type": "string", "minLength": 1},
                        "acceptanceCriteria": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "issue_id": {"type": "string"},
                    },
                },
            },
            {
                "name": "prepare_frontier",
                "description": (
                    "Acquire all leases before claiming one or two explicit "
                    "independent frontier Beads for a native delivery fan-out."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": ["workspace", "selections"],
                    "properties": {
                        "workspace": {"type": "string", "minLength": 1},
                        "selections": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 2,
                            "items": {
                                "type": "object",
                                "required": ["issue_id", "task"],
                                "properties": {
                                    "issue_id": {"type": "string"},
                                    "task": {"type": "string"},
                                    "acceptance_criteria": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            {
                "name": "checkpoint_bead",
                "description": (
                    "Append one native-workflow checkpoint to a Bead and close "
                    "only an independently accepted task."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": [
                        "workspace",
                        "issue_id",
                        "workflow_run_id",
                        "task",
                        "decision",
                        "summary",
                        "queue",
                    ],
                    "properties": {
                        "workspace": {"type": "string", "minLength": 1},
                        "issue_id": {"type": "string", "minLength": 1},
                        "workflow_run_id": {"type": "string", "minLength": 1},
                        "task": {"type": "string", "minLength": 1},
                        "decision": {
                            "type": "string",
                            "enum": [
                                "accept",
                                "revise",
                                "reject",
                                "inconclusive",
                            ],
                        },
                        "summary": {"type": "string"},
                        "stop_reason": {"type": "string"},
                        "queue": {"type": "array", "items": {"type": "object"}},
                    },
                },
            },
            {
                "name": "admit_discoveries",
                "description": (
                    "Serialize evidence-gated creation of durable discovered "
                    "issues or dependency edges. Unsupported hypotheses are rejected."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": ["workspace", "source_issue_id", "discoveries"],
                    "properties": {
                        "workspace": {"type": "string", "minLength": 1},
                        "source_issue_id": {"type": "string", "minLength": 1},
                        "discoveries": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {"type": "object"},
                        },
                    },
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "route_team":
            task = str(arguments.get("task") or "").strip()
            if not task:
                raise ValueError("task must be non-empty")
            workflow_id = str(
                arguments.get("workflow") or "security-research-forum"
            ).strip()
            workflow = self.config.workflow(workflow_id)
            eligibility_task = (
                f"security {task}" if workflow.requires_authorization else task
            )
            persona_ids = tuple(
                dict.fromkeys(
                    persona
                    for stage in workflow.stages
                    for persona in stage.personas
                )
            )
            router = FuguRouter(
                models=self.config.models,
                personas=self.config.personas,
                policy=self.config.team_policy,
                outcomes=self.store.routing_outcomes(),
                observations=self.store.routing_observations(),
            )
            distributions: dict[str, list[dict[str, Any]]] = {}
            route_adjustments: dict[tuple[str, str], float] = {}
            shadow_mode = self.config.team_policy.routing_mode == "shadow"
            for persona_id in persona_ids:
                persona = self.config.personas[persona_id]
                primary_models = tuple(
                    model_id
                    for model_id in persona.preferred_models
                    if not self.config.models[model_id].fallback_only
                )
                candidates = router.rank(
                    task=eligibility_task,
                    persona_id=persona_id,
                    model_ids=primary_models,
                )
                distributions[persona_id] = [
                    candidate.as_dict() for candidate in candidates
                ]
                if not shadow_mode:
                    for candidate in candidates:
                        route_adjustments[(persona_id, candidate.model)] = (
                            0.20 * (candidate.contextual_success - 0.5)
                            + 0.10 * (candidate.terminal_success - 0.5)
                            + 0.05 * (candidate.format_success - 0.5)
                        )
            plan = TeamComposer(
                models=self.config.models,
                personas=self.config.personas,
                policy=self.config.team_policy,
                route_adjustments=route_adjustments,
                use_behavioral_priors=not shadow_mode,
            ).compose(workflow, task)
            assignments = []
            for assignment in plan.assignments:
                route = self.config.models[assignment.model]
                agent_type = MODEL_AGENT_TYPES.get(
                    route.family, "orchestrator:opus-worker"
                )
                if route.id.startswith("fable-5"):
                    agent_type = "orchestrator:fable-neutral"
                assignments.append(
                    {
                        "persona": assignment.persona,
                        "model": assignment.model,
                        "family": route.family,
                        "agent_type": agent_type,
                        "score": assignment.score,
                        "reasons": list(assignment.reasons),
                        "fallback_order": list(assignment.fallback_order),
                        "routing_distribution": distributions[
                            assignment.persona
                        ],
                        "shadow_recommendation": (
                            distributions[assignment.persona][0]["model"]
                            if shadow_mode
                            else None
                        ),
                    }
                )
            return {
                "workflow_run_id": f"native-{uuid.uuid4().hex[:16]}",
                "task": task,
                "workflow": workflow_id,
                "total_score": plan.total_score,
                "unique_models": plan.unique_models,
                "unique_families": plan.unique_families,
                "task_traits": plan.task_traits,
                "assignments": assignments,
                "routing_mode": self.config.team_policy.routing_mode,
                "execution_plane": "claude-native-workflow",
            }
        if name == "route_persona":
            task = str(arguments.get("task") or "")
            persona_id = str(arguments.get("persona") or "").strip()
            if persona_id not in self.config.personas:
                raise ValueError(f"unknown persona: {persona_id}")
            persona = self.config.personas[persona_id]
            primary_models = tuple(
                model_id
                for model_id in persona.preferred_models
                if not self.config.models[model_id].fallback_only
            )
            recovery_models = tuple(
                model_id
                for model_id in persona.preferred_models
                if self.config.models[model_id].fallback_only
                and is_route_eligible(
                    task=task,
                    persona_id=persona_id,
                    model_id=model_id,
                    policy=self.config.team_policy,
                )
            )
            router = FuguRouter(
                models=self.config.models,
                personas=self.config.personas,
                policy=self.config.team_policy,
                outcomes=self.store.routing_outcomes(),
                observations=self.store.routing_observations(),
            )
            return {
                "task": task,
                "persona": persona_id,
                "routes": [
                    candidate.as_dict()
                    for candidate in router.rank(
                        task=task,
                        persona_id=persona_id,
                        model_ids=primary_models,
                    )
                ],
                "recovery_routes": list(recovery_models),
            }
        if name == "inspect_frontier":
            workspace = Path(str(arguments.get("workspace") or "")).expanduser()
            limit = arguments.get("limit", 8)
            return self.beads.frontier(workspace, limit)
        if name == "prepare_bead":
            workspace = Path(str(arguments.get("workspace") or "")).expanduser()
            task = str(arguments.get("task") or "").strip()
            if not task:
                raise ValueError("task must be non-empty")
            raw_acceptance = arguments.get("acceptanceCriteria") or []
            if not isinstance(raw_acceptance, list):
                raise ValueError("acceptanceCriteria must be an array")
            issue_id = str(arguments.get("issue_id") or "").strip() or None
            return self.beads.prepare(
                workspace,
                task,
                [str(item) for item in raw_acceptance],
                issue_id,
            )
        if name == "prepare_frontier":
            raw_selections = arguments.get("selections")
            if not isinstance(raw_selections, list) or not all(
                isinstance(item, dict) for item in raw_selections
            ):
                raise ValueError("selections must be an array of objects")
            workspace = Path(str(arguments.get("workspace") or "")).expanduser()
            return self.beads.prepare_frontier(workspace, raw_selections)
        if name == "admit_discoveries":
            raw_discoveries = arguments.get("discoveries")
            if not isinstance(raw_discoveries, list) or not all(
                isinstance(item, dict) for item in raw_discoveries
            ):
                raise ValueError("discoveries must be an array of objects")
            workspace = Path(str(arguments.get("workspace") or "")).expanduser()
            source_issue_id = str(arguments.get("source_issue_id") or "")
            return self.beads.admit_discoveries(
                workspace,
                source_issue_id,
                raw_discoveries,
            )
        if name == "checkpoint_bead":
            raw_queue = arguments.get("queue")
            if not isinstance(raw_queue, list) or not all(
                isinstance(item, dict) for item in raw_queue
            ):
                raise ValueError("queue must be an array of objects")
            workspace = Path(
                str(arguments.get("workspace") or "")
            ).expanduser()
            issue_id = str(arguments.get("issue_id") or "")
            workflow_run_id = str(arguments.get("workflow_run_id") or "")
            task = str(arguments.get("task") or "")
            decision = str(arguments.get("decision") or "")
            self.store.validate_native_outcome(
                workflow_run_id=workflow_run_id,
                task=task,
                decision=decision,
                queue=raw_queue,
            )
            self.beads.validate_checkpoint_target(workspace, issue_id)
            result = self.beads.checkpoint(
                workspace,
                issue_id,
                decision=decision,
                summary=str(arguments.get("summary") or ""),
                stop_reason=str(arguments.get("stop_reason") or ""),
                queue=raw_queue,
            )
            recorded = self.store.record_native_outcome(
                workflow_run_id=workflow_run_id,
                bead_id=issue_id,
                task=task,
                decision=decision,
                queue=raw_queue,
            )
            result["routing_observations_recorded"] = recorded
            return result
        raise ValueError(f"unknown tool: {name}")

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    @classmethod
    def _tool_result(
        cls,
        value: dict[str, Any],
        *,
        request_id: Any,
        is_error: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(value, indent=2, default=str),
                }
            ],
            "structuredContent": value,
        }
        if is_error:
            result["isError"] = True
        return cls._result(request_id, result)


def serve(
    server: FuguMcpServer,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> None:
    for raw_line in input_stream:
        if not raw_line.strip():
            continue
        try:
            request = json.loads(raw_line)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            response = server.handle(request)
        except (json.JSONDecodeError, ValueError) as exc:
            response = FuguMcpServer._error(None, -32700, str(exc))
        if response is not None:
            output_stream.write(json.dumps(response, separators=(",", ":")) + "\n")
            output_stream.flush()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--state", type=Path, default=default_state_path())
    args = parser.parse_args(argv)
    config = AppConfig.load(args.root)
    serve(FuguMcpServer(config, StateStore(args.state)))


if __name__ == "__main__":
    main()
