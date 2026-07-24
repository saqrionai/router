from __future__ import annotations

import json
import re
from pathlib import Path

from orchestrator.store import StateStore


def render_bundle(store: StateStore, run_id: str) -> str:
    run = store.run(run_id)
    messages = store.messages(run_id)
    artifacts = store.artifacts(run_id)
    checks = store.checks(run_id)
    usage = store.usage_summary(run_id)
    tracking = run.get("tracking") or {}
    tracking_ref = (
        f"{tracking.get('system')}:{tracking.get('issue_id')}"
        if tracking
        else "none"
    )
    lines = [
        "# Orchestrator Context Bundle",
        "",
        f"- Run: `{run_id}`",
        f"- Workflow: `{run['workflow']}`",
        f"- Status: `{run['status']}`",
        f"- Decision: `{run.get('decision') or 'pending'}`",
        f"- Workspace: `{run['workspace']}`",
        f"- Current round: `{run['current_round']}`",
        f"- Tracking: `{tracking_ref}`",
        "",
        "## Task",
        "",
        run["task"],
        "",
        "## Scope",
        "",
        "```json",
        json.dumps(run["scope"], indent=2, sort_keys=True),
        "```",
        "",
        "## Usage",
        "",
    ]
    if usage:
        lines.extend(
            [
                "| Persona | Model | Backend | Calls | Input | Output | Cache read | Cache write | CLI estimate |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in usage:
            lines.append(
                "| {persona} | {model} | {backend} | {calls} | {input_tokens} | "
                "{output_tokens} | {cache_read_tokens} | {cache_write_tokens} | "
                "${estimated_cost_usd:.4f} |".format(**item)
            )
    else:
        lines.append("(no model usage recorded)")
    lines.extend(["", "## Board", ""])
    for message in messages:
        lines.extend(
            [
                f"### #{message['id']} {message['author']} / {message['kind']}",
                "",
                f"- Round: {message['round_number']} | Stage: `{message['stage']}` | Thread: `{message['thread']}`",
                f"- Recipients: {', '.join(message['recipients'])}",
                "",
                message["body"],
                "",
            ]
        )
    lines.extend(["## Artifacts", ""])
    if not artifacts:
        lines.append("(no artifacts published)")
    for artifact in artifacts:
        source_ids = ", ".join(
            f"#{message_id}" for message_id in artifact["source_message_ids"]
        ) or "none"
        lines.extend(
            [
                f"### A{artifact['id']} {artifact['title']}",
                "",
                f"- Author: `{artifact['author']}` | Kind: `{artifact['kind']}` | Thread: `{artifact['thread']}`",
                f"- Attached post: `#{artifact['message_id']}` | Sources: {source_ids}",
                f"- Media type: `{artifact['media_type']}`",
                "",
                f"```{_artifact_fence_language(artifact['media_type'])}",
                artifact["content"],
                "```",
                "",
            ]
        )
    lines.extend(["## Machine Checks", ""])
    if not checks:
        lines.append("(no checks configured or recorded)")
    for check in checks:
        lines.extend(
            [
                f"### {check['name']}: {check['status']}",
                "",
                f"Command: `{' '.join(check['argv'])}`",
                f"Exit code: `{check['exit_code']}`",
                "",
                "```text",
                check["stdout"] or check["stderr"] or "(no output)",
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Rehydration Instruction",
            "",
            "Continue from this durable run state. Treat model messages as claims, not facts. "
            "Preserve message ids when citing prior work, rely on machine-check messages for "
            "execution truth, and publish new evidence or disagreements as new messages instead "
            "of silently rewriting history.",
            "",
        ]
    )
    return "\n".join(lines)


def write_bundle(store: StateStore, run_id: str, path: Path) -> Path:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_bundle(store, run_id), encoding="utf-8")
    return path


def write_artifacts(
    store: StateStore, run_id: str, directory: Path
) -> list[Path]:
    directory = directory.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for artifact in store.artifacts(run_id):
        slug = re.sub(r"[^a-z0-9]+", "-", artifact["title"].lower()).strip("-")
        slug = slug[:64] or "artifact"
        extension = _artifact_extension(artifact["media_type"])
        path = directory / f"A{artifact['id']}-{slug}.{extension}"
        path.write_text(artifact["content"], encoding="utf-8")
        written.append(path)
    return written


def _artifact_fence_language(media_type: str) -> str:
    return {
        "application/json": "json",
        "text/markdown": "markdown",
        "text/x-diff": "diff",
        "text/x-python": "python",
        "text/x-shellscript": "bash",
    }.get(media_type, "text")


def _artifact_extension(media_type: str) -> str:
    return {
        "application/json": "json",
        "text/csv": "csv",
        "text/markdown": "md",
        "text/x-diff": "patch",
        "text/x-python": "py",
        "text/x-shellscript": "sh",
    }.get(media_type, "txt")
