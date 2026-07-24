#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_MESSAGE_CHARS = 65_536


def state_path() -> Path:
    root = Path(
        os.environ.get(
            "ORCHESTRATOR_STATE_DIR",
            Path.home() / ".local" / "state" / "orchestrator",
        )
    ).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root / "claude-native-events.jsonl"


def compact_event(payload: dict[str, Any]) -> dict[str, Any]:
    event = dict(payload)
    message = event.get("last_assistant_message")
    if isinstance(message, str) and len(message) > MAX_MESSAGE_CHARS:
        event["last_assistant_message"] = message[:MAX_MESSAGE_CHARS]
        event["last_assistant_message_truncated"] = len(message) - MAX_MESSAGE_CHARS
    event["recorded_at"] = datetime.now(timezone.utc).isoformat()
    event["execution_plane"] = "claude-native-workflow"
    return event


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
        with state_path().open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(compact_event(payload), default=str) + "\n")
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
