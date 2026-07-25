from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.beads import BeadsBridge, BeadsError
from orchestrator.config import AppConfig
from orchestrator.mcp_server import FuguMcpServer
from orchestrator.store import StateStore


def run(workspace: Path, *argv: str) -> str:
    completed = subprocess.run(
        argv,
        cwd=workspace,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


@pytest.mark.skipif(shutil.which("bd") is None, reason="bd is not installed")
def test_auto_selection_resumes_work_and_skips_live_lease(
    tmp_path: Path,
) -> None:
    run(tmp_path, "git", "init", "-q")
    run(tmp_path, "git", "config", "user.name", "Saqrion Test")
    run(tmp_path, "git", "config", "user.email", "test@example.invalid")
    run(
        tmp_path,
        "bd",
        "init",
        "--non-interactive",
        "--skip-agents",
        "--skip-hooks",
        "--prefix",
        "auto",
        "--quiet",
    )
    ready_id = run(
        tmp_path,
        "bd",
        "create",
        "Highest priority ready work",
        "--priority",
        "0",
        "--description",
        "Implement the ready item.",
        "--acceptance",
        "ready behavior is verified",
        "--silent",
    )
    active_id = run(
        tmp_path,
        "bd",
        "create",
        "Previously active work",
        "--priority",
        "2",
        "--description",
        "Resume the previous implementation.",
        "--acceptance",
        "previous behavior is verified",
        "--silent",
    )
    run(tmp_path, "bd", "update", active_id, "--claim")

    first = BeadsBridge()
    second = BeadsBridge()
    first_result = first.prepare(tmp_path, "continue", [])
    second_result = second.prepare(tmp_path, "continue", [])

    assert first_result["issue_id"] == active_id
    assert first_result["selection"] == "resumed-in-progress"
    assert "Resume the previous implementation." in first_result["resolved_task"]
    assert first_result["resolved_acceptance_criteria"] == [
        "previous behavior is verified"
    ]
    assert second_result["issue_id"] == ready_id
    assert second_result["selection"] == "claimed-ready"

    state = StateStore(tmp_path / "orchestrator-state.db")
    server = FuguMcpServer(
        AppConfig.load(),
        state,
    )
    with pytest.raises(ValueError, match="workflow_run_id"):
        server.call_tool(
            "checkpoint_bead",
            {
                "workspace": str(tmp_path),
                "issue_id": active_id,
                "workflow_run_id": "",
                "task": "verify persistence ordering",
                "decision": "accept",
                "summary": "must not mutate Beads",
                "stop_reason": "accepted",
                "queue": [],
            },
        )
    assert json.loads(
        run(tmp_path, "bd", "comments", active_id, "--json")
    ) == []
    active_before_checkpoint = json.loads(
        run(tmp_path, "bd", "show", active_id, "--json")
    )[0]
    assert active_before_checkpoint["status"] == "in_progress"
    with pytest.raises(BeadsError):
        server.call_tool(
            "checkpoint_bead",
            {
                "workspace": str(tmp_path),
                "issue_id": "auto-does-not-exist",
                "workflow_run_id": "native-invalid-target",
                "task": "verify target ordering",
                "decision": "accept",
                "summary": "must not train the router",
                "stop_reason": "accepted",
                "queue": [
                    {
                        "id": "unit-1",
                        "round": 1,
                        "persona": "verifier",
                        "model": "opus-5-bounded",
                        "status": "accepted",
                    }
                ],
            },
        )
    assert state.routing_observations() == []

    with pytest.raises(ValueError, match="round must be an integer"):
        server.call_tool(
            "checkpoint_bead",
            {
                "workspace": str(tmp_path),
                "issue_id": active_id,
                "workflow_run_id": "native-invalid-round",
                "task": "verify queue prevalidation",
                "decision": "revise",
                "summary": "must not mutate Beads",
                "stop_reason": "infrastructure-failure",
                "queue": [
                    {
                        "id": "unit-1",
                        "round": "bad",
                        "persona": "verifier",
                        "model": "opus-5-bounded",
                        "status": "verified",
                    }
                ],
            },
        )
    assert json.loads(
        run(tmp_path, "bd", "comments", active_id, "--json")
    ) == []
    assert state.routing_observations() == []

    original_checkpoint = server.beads.checkpoint

    def fail_checkpoint(*args: object, **kwargs: object) -> dict[str, object]:
        raise BeadsError("simulated checkpoint failure")

    server.beads.checkpoint = fail_checkpoint  # type: ignore[method-assign]
    with pytest.raises(BeadsError, match="simulated checkpoint failure"):
        server.call_tool(
            "checkpoint_bead",
            {
                "workspace": str(tmp_path),
                "issue_id": active_id,
                "workflow_run_id": "native-beads-failure",
                "task": "verify Beads-first persistence",
                "decision": "revise",
                "summary": "do not train before Beads",
                "stop_reason": "infrastructure-failure",
                "queue": [
                    {
                        "id": "unit-1",
                        "round": 1,
                        "persona": "verifier",
                        "model": "opus-5-bounded",
                        "status": "verified",
                    }
                ],
            },
        )
    server.beads.checkpoint = original_checkpoint  # type: ignore[method-assign]
    assert state.routing_observations() == []

    first.checkpoint(
        tmp_path,
        active_id,
        decision="accept",
        summary="verified active work",
        stop_reason="accepted",
        queue=[
            {
                "id": "unit-1",
                "status": "accepted",
                "routeAttempts": [
                    {
                        "model": "fable-5-bounded",
                        "outcome": "degraded",
                        "reasons": ["passed criterion has no evidence"],
                    },
                    {
                        "model": "opus-4.8-bounded",
                        "outcome": "usable",
                        "reasons": [],
                    },
                ],
            }
        ],
    )
    second.checkpoint(
        tmp_path,
        ready_id,
        decision="accept",
        summary="verified ready work",
        stop_reason="accepted",
        queue=[],
    )
    comments = json.loads(
        run(tmp_path, "bd", "comments", active_id, "--json")
    )
    rendered_comments = json.dumps(comments)
    assert "fable-5-bounded" in rendered_comments
    assert "opus-4.8-bounded" in rendered_comments
    assert "usable" in rendered_comments
    assert "passed criterion has no evidence" in rendered_comments

    empty_result = BeadsBridge().prepare(tmp_path, "continue", [])

    assert empty_result["launch_allowed"] is False
    assert empty_result["selection"] == "queue-empty"
