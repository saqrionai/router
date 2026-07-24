from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.beads import BeadsBridge


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

    first.checkpoint(
        tmp_path,
        active_id,
        decision="accept",
        summary="verified active work",
        stop_reason="accepted",
        queue=[],
    )
    second.checkpoint(
        tmp_path,
        ready_id,
        decision="accept",
        summary="verified ready work",
        stop_reason="accepted",
        queue=[],
    )

    empty_result = BeadsBridge().prepare(tmp_path, "continue", [])

    assert empty_result["launch_allowed"] is False
    assert empty_result["selection"] == "queue-empty"
