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
                        "version": "0.1.0",
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
                "name": "prepare_bead",
                "description": (
                    "Claim an existing Bead or create one for a Claude native "
                    "workflow. This records durable project state but never "
                    "launches a model or scheduler."
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
            for persona_id in persona_ids:
                persona = self.config.personas[persona_id]
                candidates = router.rank(
                    task=task,
                    persona_id=persona_id,
                    model_ids=persona.preferred_models,
                )
                distributions[persona_id] = [
                    candidate.as_dict() for candidate in candidates
                ]
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
                "execution_plane": "claude-native-workflow",
            }
        if name == "route_persona":
            task = str(arguments.get("task") or "")
            persona_id = str(arguments.get("persona") or "").strip()
            if persona_id not in self.config.personas:
                raise ValueError(f"unknown persona: {persona_id}")
            persona = self.config.personas[persona_id]
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
                        model_ids=persona.preferred_models,
                    )
                ],
            }
        if name == "prepare_bead":
            workspace = Path(str(arguments.get("workspace") or "")).expanduser()
            task = str(arguments.get("task") or "").strip()
            if not task:
                raise ValueError("task must be non-empty")
            raw_acceptance = arguments.get("acceptanceCriteria") or []
            if not isinstance(raw_acceptance, list):
                raise ValueError("acceptanceCriteria must be an array")
            issue_id = str(arguments.get("issue_id") or "").strip() or None
            return BeadsBridge().prepare(
                workspace,
                task,
                [str(item) for item in raw_acceptance],
                issue_id,
            )
        if name == "checkpoint_bead":
            raw_queue = arguments.get("queue")
            if not isinstance(raw_queue, list) or not all(
                isinstance(item, dict) for item in raw_queue
            ):
                raise ValueError("queue must be an array of objects")
            result = BeadsBridge().checkpoint(
                Path(str(arguments.get("workspace") or "")).expanduser(),
                str(arguments.get("issue_id") or ""),
                decision=str(arguments.get("decision") or ""),
                summary=str(arguments.get("summary") or ""),
                stop_reason=str(arguments.get("stop_reason") or ""),
                queue=raw_queue,
            )
            result["routing_observations_recorded"] = (
                self.store.record_native_outcome(
                    workflow_run_id=str(arguments.get("workflow_run_id") or ""),
                    bead_id=str(arguments.get("issue_id") or ""),
                    task=str(arguments.get("task") or ""),
                    decision=str(arguments.get("decision") or ""),
                    queue=raw_queue,
                )
            )
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
