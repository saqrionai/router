from __future__ import annotations

import io
import json
from pathlib import Path

from orchestrator.config import AppConfig
from orchestrator.mcp_server import FuguMcpServer, serve
from orchestrator.store import StateStore


ROOT = Path(__file__).resolve().parents[1]


def server(tmp_path: Path) -> FuguMcpServer:
    return FuguMcpServer(
        AppConfig.load(ROOT),
        StateStore(tmp_path / "orchestrator.db"),
    )


def test_route_team_maps_models_to_native_agent_types(tmp_path: Path) -> None:
    payload = server(tmp_path).call_tool(
        "route_team",
        {
            "task": (
                "authorized security reverse engineering with implementation "
                "and independent verification"
            ),
            "workflow": "security-research-forum",
        },
    )

    assignments = {
        item["persona"]: item for item in payload["assignments"]
    }
    assert payload["workflow_run_id"].startswith("native-")
    assert payload["execution_plane"] == "claude-native-workflow"
    assert payload["routing_mode"] == "shadow"
    assert assignments["researcher"]["agent_type"] == "orchestrator:opus-worker"
    for assignment in assignments.values():
        assert assignment["model"] != "opus-4.8-bounded"
        assert assignment["fallback_order"][-1] == "opus-4.8-bounded"
    assert assignments["engineer"]["agent_type"] == "orchestrator:codex-worker"
    assert assignments["verifier"]["agent_type"] == "orchestrator:opus-worker"
    assert assignments["researcher"]["routing_distribution"]
    assert assignments["researcher"]["shadow_recommendation"]


def test_security_workflow_excludes_fable_for_neutral_task_text(
    tmp_path: Path,
) -> None:
    payload = server(tmp_path).call_tool(
        "route_team",
        {
            "task": "compare my patch with the maintainer patch",
            "workflow": "security-research-forum",
        },
    )

    for assignment in payload["assignments"]:
        assert assignment["model"] != "fable-5-bounded"
        assert "fable-5-bounded" not in assignment["fallback_order"]
        assert all(
            candidate["model"] != "fable-5-bounded"
            for candidate in assignment["routing_distribution"]
        )


def test_stdio_protocol_lists_and_calls_tools(tmp_path: Path) -> None:
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "route_team",
                "arguments": {
                    "task": "research and verify a large codebase",
                    "workflow": "security-research-forum",
                },
            },
        },
    ]
    input_stream = io.StringIO(
        "".join(json.dumps(request) + "\n" for request in requests)
    )
    output_stream = io.StringIO()

    serve(server(tmp_path), input_stream, output_stream)

    responses = [
        json.loads(line) for line in output_stream.getvalue().splitlines()
    ]
    assert [response["id"] for response in responses] == [1, 2, 3]
    assert responses[0]["result"]["serverInfo"]["name"] == "orchestrator-fugu"
    tool_names = {
        tool["name"] for tool in responses[1]["result"]["tools"]
    }
    assert tool_names == {
        "route_team",
        "route_persona",
        "inspect_frontier",
        "prepare_bead",
        "prepare_frontier",
        "checkpoint_bead",
    }
    assert (
        responses[2]["result"]["structuredContent"]["execution_plane"]
        == "claude-native-workflow"
    )


def test_route_persona_returns_json_ready_candidates(tmp_path: Path) -> None:
    payload = server(tmp_path).call_tool(
        "route_persona",
        {"task": "verify a large codebase", "persona": "verifier"},
    )

    assert payload["routes"]
    assert all(isinstance(candidate, dict) for candidate in payload["routes"])
    json.dumps(payload)


def test_prepare_bead_is_disabled_outside_a_beads_workspace(
    tmp_path: Path,
) -> None:
    payload = server(tmp_path).call_tool(
        "prepare_bead",
        {
            "workspace": str(tmp_path),
            "task": "verify the native workflow",
            "acceptanceCriteria": ["the native workflow passes"],
        },
    )

    assert payload["enabled"] is False
    assert "no .beads directory" in payload["reason"]


def test_inspect_frontier_is_read_only_and_disabled_outside_beads(
    tmp_path: Path,
) -> None:
    payload = server(tmp_path).call_tool(
        "inspect_frontier",
        {"workspace": str(tmp_path), "limit": 8},
    )

    assert payload["enabled"] is False
    assert "no .beads directory" in payload["reason"]
