from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


class BeadsError(RuntimeError):
    pass


class BeadsBridge:
    """Read a frozen Beads snapshot and append compact run summaries."""

    ISSUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def available(self, workspace: Path) -> bool:
        resolved = workspace.expanduser().resolve()
        home = Path.home().resolve()
        for candidate in (resolved, *resolved.parents):
            if candidate == home and resolved != home:
                break
            if (candidate / ".beads").is_dir():
                return True
        return False

    def prepare(
        self,
        workspace: Path,
        task: str,
        acceptance_criteria: list[str],
        issue_id: str | None = None,
    ) -> dict[str, Any]:
        workspace = workspace.expanduser().resolve()
        if not self.available(workspace):
            return {
                "enabled": False,
                "reason": f"no .beads directory under {workspace}",
            }
        if issue_id:
            self._validate_issue_id(issue_id)
            snapshot = self.snapshot(workspace, issue_id)
            if snapshot.get("status") == "in_progress":
                return {
                    "enabled": True,
                    "launch_allowed": False,
                    "issue_id": issue_id,
                    "snapshot": snapshot,
                    "reason": (
                        "Bead is already in_progress; resume its existing native "
                        "workflow instead of launching a duplicate"
                    ),
                }
            if snapshot.get("status") != "open":
                return {
                    "enabled": True,
                    "launch_allowed": False,
                    "issue_id": issue_id,
                    "snapshot": snapshot,
                    "reason": (
                        f"Bead status is {snapshot.get('status')!r}; explicitly "
                        "reopen it before launching a new workflow"
                    ),
                }
        else:
            title = " ".join(task.split())[:120] or "Native orchestrator task"
            argv = [
                "bd",
                "create",
                title,
                "--description",
                task[:12_000],
                "--labels",
                "orchestrator,native-workflow",
                "--silent",
            ]
            acceptance = "\n".join(
                f"- {item}" for item in acceptance_criteria if item.strip()
            )
            if acceptance:
                argv.extend(["--acceptance", acceptance[:12_000]])
            completed = self._run(workspace, argv)
            issue_id = completed.stdout.strip().splitlines()[-1]
            self._validate_issue_id(issue_id)
        self._run(workspace, ["bd", "update", issue_id, "--claim"])
        return {
            "enabled": True,
            "launch_allowed": True,
            "issue_id": issue_id,
            "snapshot": self.snapshot(workspace, issue_id),
        }

    def checkpoint(
        self,
        workspace: Path,
        issue_id: str,
        *,
        decision: str,
        summary: str,
        stop_reason: str,
        queue: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self._validate_issue_id(issue_id)
        completed_units = sum(
            1
            for item in queue
            if str(item.get("status")) in {"returned", "verified", "accepted"}
        )
        comment = (
            "Claude native workflow checkpoint\n\n"
            f"- Decision: {decision}\n"
            f"- Stop reason: {stop_reason or 'none'}\n"
            f"- Queue: {completed_units}/{len(queue)} units returned or verified\n"
            f"- Summary: {summary.strip()[:8_000] or 'No summary returned.'}"
        )
        self.comment(workspace, issue_id, comment)
        if decision == "accept":
            self._run(
                workspace,
                [
                    "bd",
                    "close",
                    issue_id,
                    "--reason",
                    f"Native workflow accepted: {summary.strip()[:500]}",
                ],
            )
            status = "closed"
        elif stop_reason in {
            "no-progress",
            "round-limit",
            "rejected",
            "inconclusive",
        }:
            self._run(workspace, ["bd", "update", issue_id, "--status", "blocked"])
            status = "blocked"
        else:
            status = "in_progress"
        return {"enabled": True, "issue_id": issue_id, "status": status}

    def snapshot(self, workspace: Path, issue_id: str) -> dict[str, Any]:
        self._validate_issue_id(issue_id)
        completed = self._run(workspace, ["bd", "show", issue_id, "--json"])
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise BeadsError("bd show returned invalid JSON") from exc
        if isinstance(payload, list):
            payload = payload[0] if payload else None
        if not isinstance(payload, dict):
            raise BeadsError(f"Bead does not exist: {issue_id}")
        return self._bounded_snapshot(payload)

    def comment(self, workspace: Path, issue_id: str, body: str) -> None:
        self._validate_issue_id(issue_id)
        self._run(workspace, ["bd", "comments", "add", issue_id, body])

    @classmethod
    def _validate_issue_id(cls, issue_id: str) -> None:
        if not cls.ISSUE_ID.fullmatch(issue_id):
            raise BeadsError(f"invalid Bead issue id: {issue_id!r}")

    @staticmethod
    def _bounded_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
        fields = (
            "id",
            "title",
            "status",
            "priority",
            "issue_type",
            "description",
            "acceptance_criteria",
            "design",
            "notes",
            "dependencies",
            "dependents",
        )
        snapshot: dict[str, Any] = {}
        for field in fields:
            value = payload.get(field)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, str) and len(value) > 12_000:
                value = value[:12_000] + "\n[truncated by Orchestrator]"
            snapshot[field] = value
        return snapshot

    @staticmethod
    def _run(
        workspace: Path, argv: list[str]
    ) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                argv,
                cwd=workspace,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except FileNotFoundError as exc:
            raise BeadsError("bd command is not installed") from exc
        except subprocess.TimeoutExpired as exc:
            raise BeadsError("bd command timed out") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise BeadsError(f"{' '.join(argv[:3])} failed: {detail}")
        return completed
