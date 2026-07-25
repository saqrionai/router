from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE = ROOT / "claude-plugin" / "hooks" / "lifecycle.py"


def invoke(payload: dict[str, object], state_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ORCHESTRATOR_STATE_DIR"] = str(state_dir)
    return subprocess.run(
        ["python3", str(LIFECYCLE)],
        input=json.dumps(payload),
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def test_native_hook_updates_normalized_agent_heartbeat(tmp_path: Path) -> None:
    start = {
        "hook_event_name": "SubagentStart",
        "session_id": "session-1",
        "agent_id": "agent-1",
        "agent_type": "orchestrator:opus-worker",
        "cwd": str(tmp_path),
        "transcript_path": str(tmp_path / "session.jsonl"),
    }
    invoke(start, tmp_path)
    heartbeat_path = tmp_path / "heartbeats" / "session-1" / "agent-1.json"
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    assert heartbeat["state"] == "running"
    assert heartbeat["event"] == "SubagentStart"

    invoke(
        {
            **start,
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_result": "completed",
        },
        tmp_path,
    )
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    assert heartbeat["state"] == "running"
    assert heartbeat["event"] == "PostToolUse"
    assert heartbeat["tool_name"] == "Bash"

    invoke({**start, "hook_event_name": "SubagentStop"}, tmp_path)
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    assert heartbeat["state"] == "completed"
    assert heartbeat["event"] == "SubagentStop"
