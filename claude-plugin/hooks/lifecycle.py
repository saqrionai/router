#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_MESSAGE_CHARS = 65_536
MAX_TOOL_CHARS = 16_384


def state_root() -> Path:
    root = Path(
        os.environ.get(
            "ORCHESTRATOR_STATE_DIR",
            Path.home() / ".local" / "state" / "orchestrator",
        )
    ).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def state_path() -> Path:
    return state_root() / "claude-native-events.jsonl"


def heartbeat_root() -> Path:
    root = state_root() / "heartbeats"
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_component(value: str) -> str:
    rendered = "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in value
    )
    return rendered[:160] or "unknown"


def compact_event(payload: dict[str, Any]) -> dict[str, Any]:
    event = dict(payload)
    message = event.get("last_assistant_message")
    if isinstance(message, str) and len(message) > MAX_MESSAGE_CHARS:
        event["last_assistant_message"] = message[:MAX_MESSAGE_CHARS]
        event["last_assistant_message_truncated"] = len(message) - MAX_MESSAGE_CHARS
    for key in ("tool_input", "tool_result"):
        value = event.get(key)
        if value is None:
            continue
        rendered = value if isinstance(value, str) else json.dumps(value, default=str)
        if len(rendered) > MAX_TOOL_CHARS:
            event[key] = rendered[:MAX_TOOL_CHARS]
            event[f"{key}_truncated"] = len(rendered) - MAX_TOOL_CHARS
    event["recorded_at"] = datetime.now(timezone.utc).isoformat()
    event["execution_plane"] = "claude-native-workflow"
    return event


def heartbeat(payload: dict[str, Any], recorded_at: str) -> dict[str, Any]:
    event_name = str(payload.get("hook_event_name") or "unknown")
    state = (
        "completed"
        if event_name in {"SubagentStop", "SessionEnd"}
        else "running"
    )
    return {
        "schema_version": 1,
        "source": "claude-native-hook",
        "execution_plane": "claude-native-workflow",
        "session_id": str(payload.get("session_id") or "unknown"),
        "agent_id": str(payload.get("agent_id") or "main"),
        "agent_type": str(payload.get("agent_type") or ""),
        "state": state,
        "event": event_name,
        "tool_name": str(payload.get("tool_name") or ""),
        "last_progress_at": recorded_at,
        "cwd": str(payload.get("cwd") or ""),
        "transcript_path": str(payload.get("transcript_path") or ""),
    }


def write_heartbeat(payload: dict[str, Any], recorded_at: str) -> None:
    value = heartbeat(payload, recorded_at)
    session = safe_component(value["session_id"])
    agent = safe_component(value["agent_id"])
    directory = heartbeat_root() / session
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{agent}.json"
    temporary = directory / f".{agent}.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, destination)


def context_for(agent_type: str) -> str:
    base = (
        "You are running under the Orchestrator Fugu native workflow. "
        "Keep observed evidence, inference, and hypothesis separate. "
        "Do not self-attest: cite real artifacts and command output, and state "
        "what remains unverified. The workflow, not the subagent, owns spawning "
        "and retry loops."
    )
    if "fable-neutral" in agent_type:
        return (
            base
            + " For cybersecurity work you are neutral-only: verify supplied "
            "claims and evidence, but do not originate new exploit chains, "
            "payloads, evasion methods, or operational attack steps."
        )
    return base


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook payload must be an object")
        event = compact_event(payload)
        with state_path().open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, default=str) + "\n")
        write_heartbeat(payload, str(event["recorded_at"]))
        if payload.get("hook_event_name") == "SubagentStart":
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "SubagentStart",
                            "additionalContext": context_for(
                                str(payload.get("agent_type") or "")
                            ),
                        }
                    }
                )
            )
    except Exception as exc:
        print(f"orchestrator lifecycle telemetry failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
