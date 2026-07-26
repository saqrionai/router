from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, TextIO


class BeadsError(RuntimeError):
    pass


def resolve_bd_binary() -> str | None:
    """Resolve one stable Beads executable for setup and runtime calls."""
    configured = os.environ.get("ORCHESTRATOR_BD_BIN", "").strip()
    if configured:
        return str(Path(configured).expanduser())
    for candidate in (
        Path("/opt/homebrew/bin/bd"),
        Path("/usr/local/bin/bd"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("bd")


class BeadsBridge:
    """Read a frozen Beads snapshot and append compact run summaries."""

    ISSUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    CONTINUATION = re.compile(
        r"\b(continue|resume|keep going|pick up where|next bead|next task)\b",
        re.IGNORECASE,
    )
    DISCOVERY_REASONS = {
        "deliverable",
        "reproducible-blocker",
        "independently-actionable-investigation",
    }
    EVIDENCE_TYPES = {"artifact", "command", "test", "device", "log"}

    def __init__(self) -> None:
        self._leases: dict[tuple[Path, str], TextIO] = {}

    def available(self, workspace: Path) -> bool:
        return self._beads_root(workspace) is not None

    def _beads_root(self, workspace: Path) -> Path | None:
        resolved = workspace.expanduser().resolve()
        home = Path.home().resolve()
        for candidate in (resolved, *resolved.parents):
            if candidate == home and resolved != home:
                break
            if (candidate / ".beads").is_dir():
                return candidate
        return None

    def prepare(
        self,
        workspace: Path,
        task: str,
        acceptance_criteria: list[str],
        issue_id: str | None = None,
    ) -> dict[str, Any]:
        workspace = workspace.expanduser().resolve()
        beads_root = self._beads_root(workspace)
        if beads_root is None:
            return {
                "enabled": False,
                "reason": f"no .beads directory under {workspace}",
            }
        with self._workspace_lock(beads_root):
            return self._prepare_locked(
                workspace,
                beads_root,
                task,
                acceptance_criteria,
                issue_id,
            )

    def frontier(self, workspace: Path, limit: int = 8) -> dict[str, Any]:
        """Return a bounded, deterministic Bead frontier without claiming work."""
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit must be an integer")
        if limit < 1 or limit > 16:
            raise ValueError("limit must be between 1 and 16")
        workspace = workspace.expanduser().resolve()
        beads_root = self._beads_root(workspace)
        if beads_root is None:
            return {
                "enabled": False,
                "reason": f"no .beads directory under {workspace}",
            }
        with self._workspace_lock(beads_root):
            candidates, candidate_counts = self._selection_candidates(workspace)
        ranked = self.rank_candidates(candidates)
        unique: dict[str, dict[str, Any]] = {}
        for candidate in ranked:
            issue_id = str(candidate.get("id") or "")
            self._validate_issue_id(issue_id)
            unique.setdefault(issue_id, candidate)
        bounded = [
            self._frontier_candidate(candidate)
            for candidate in list(unique.values())[:limit]
        ]
        return {
            "enabled": True,
            "workspace": str(workspace),
            "candidate_counts": candidate_counts,
            "eligible_count": len(unique),
            "returned_count": len(bounded),
            "limit": limit,
            "ranking": (
                "in_progress first, then priority ascending, updated_at "
                "descending, and issue id ascending"
            ),
            "read_only": True,
            "candidates": bounded,
        }

    def prepare_frontier(
        self,
        workspace: Path,
        selections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Acquire every lease before claiming up to two frontier Beads."""
        if not 1 <= len(selections) <= 2:
            raise ValueError("selections must contain between 1 and 2 items")
        workspace = workspace.expanduser().resolve()
        beads_root = self._beads_root(workspace)
        if beads_root is None:
            return {
                "enabled": False,
                "reason": f"no .beads directory under {workspace}",
            }
        normalized: list[tuple[str, str, list[str]]] = []
        for item in selections:
            issue_id = str(item.get("issue_id") or "").strip()
            task = str(item.get("task") or "").strip()
            raw_acceptance = item.get("acceptance_criteria") or []
            self._validate_issue_id(issue_id)
            if not task:
                raise ValueError(f"{issue_id}: task must be non-empty")
            if not isinstance(raw_acceptance, list):
                raise ValueError(
                    f"{issue_id}: acceptance_criteria must be an array"
                )
            normalized.append(
                (issue_id, task, [str(value) for value in raw_acceptance])
            )
        issue_ids = [issue_id for issue_id, _, _ in normalized]
        if len(set(issue_ids)) != len(issue_ids):
            raise ValueError("frontier selections must have unique issue IDs")

        acquired: list[str] = []
        with self._workspace_lock(beads_root):
            snapshots: dict[str, dict[str, Any]] = {}
            for issue_id in issue_ids:
                snapshot = self.snapshot(workspace, issue_id)
                if snapshot.get("status") not in {"open", "in_progress"}:
                    return {
                        "enabled": True,
                        "launch_allowed": False,
                        "issue_id": issue_id,
                        "reason": (
                            f"Bead status is {snapshot.get('status')!r}; "
                            "explicitly reopen it before launching"
                        ),
                    }
                snapshots[issue_id] = snapshot
            for issue_id in issue_ids:
                if not self._acquire_issue_lease(beads_root, issue_id):
                    for acquired_id in acquired:
                        self._release_issue_lease(beads_root, acquired_id)
                    return {
                        "enabled": True,
                        "launch_allowed": False,
                        "active_issue_ids": [issue_id],
                        "reason": (
                            "A selected Bead already has an active "
                            "Orchestrator workflow"
                        ),
                    }
                acquired.append(issue_id)
            try:
                prepared = []
                for issue_id, task, acceptance in normalized:
                    snapshot = snapshots[issue_id]
                    selection = "resumed-frontier"
                    if snapshot.get("status") == "open":
                        self._run(
                            workspace,
                            ["bd", "update", issue_id, "--claim"],
                        )
                        snapshot = self.snapshot(workspace, issue_id)
                        selection = "claimed-frontier"
                    prepared.append(
                        {
                            "enabled": True,
                            "launch_allowed": True,
                            "issue_id": issue_id,
                            "selection": selection,
                            "resolved_task": self._resolved_task(task, snapshot),
                            "resolved_acceptance_criteria": (
                                self._resolved_acceptance(snapshot, acceptance)
                            ),
                            "snapshot": snapshot,
                        }
                    )
            except Exception:
                for issue_id in acquired:
                    self._release_issue_lease(beads_root, issue_id)
                raise
        return {
            "enabled": True,
            "launch_allowed": True,
            "atomic_leases": True,
            "issues": prepared,
        }

    def admit_discoveries(
        self,
        workspace: Path,
        source_issue_id: str,
        discoveries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Persist only reproducible, non-duplicate workflow discoveries."""
        self._validate_issue_id(source_issue_id)
        if len(discoveries) > 8:
            raise ValueError("at most 8 discoveries may be admitted per call")
        workspace = workspace.expanduser().resolve()
        beads_root = self._beads_root(workspace)
        if beads_root is None:
            return {
                "enabled": False,
                "reason": f"no .beads directory under {workspace}",
            }
        with self._workspace_lock(beads_root):
            self.snapshot(workspace, source_issue_id)
            existing = self._list_issues(
                workspace,
                ["bd", "list", "--all", "--json", "--limit", "0"],
            )
            title_ids = {
                self._title_fingerprint(str(item.get("title") or "")): str(
                    item.get("id") or ""
                )
                for item in existing
                if item.get("title") and item.get("id")
            }
            admitted: list[dict[str, Any]] = []
            rejected: list[dict[str, Any]] = []
            for index, discovery in enumerate(discoveries):
                kind = str(discovery.get("kind") or "").strip()
                try:
                    if kind == "issue":
                        result = self._admit_issue(
                            workspace,
                            source_issue_id,
                            discovery,
                            title_ids,
                        )
                    elif kind == "dependency":
                        result = self._admit_dependency(workspace, discovery)
                    else:
                        raise ValueError("kind must be issue or dependency")
                except (BeadsError, ValueError) as exc:
                    rejected.append(
                        {
                            "index": index,
                            "kind": kind or "unknown",
                            "reason": str(exc),
                        }
                    )
                    continue
                admitted.append(result)
            if admitted:
                lines = [
                    "Evidence-gated workflow discoveries admitted",
                    "",
                    *(
                        f"- {item['kind']}: "
                        f"{item.get('issue_id') or item.get('edge')}"
                        for item in admitted
                    ),
                ]
                self.comment(workspace, source_issue_id, "\n".join(lines))
        return {
            "enabled": True,
            "source_issue_id": source_issue_id,
            "admitted": admitted,
            "rejected": rejected,
            "admitted_count": len(admitted),
            "rejected_count": len(rejected),
        }

    def _admit_issue(
        self,
        workspace: Path,
        source_issue_id: str,
        discovery: dict[str, Any],
        title_ids: dict[str, str],
    ) -> dict[str, Any]:
        title = " ".join(str(discovery.get("title") or "").split())
        description = str(discovery.get("description") or "").strip()
        reason = str(discovery.get("durable_reason") or "").strip()
        acceptance = discovery.get("acceptance_criteria")
        check = str(discovery.get("reproducible_check") or "").strip()
        evidence = self._validated_discovery_evidence(discovery.get("evidence"))
        if len(title) < 8 or len(title) > 120:
            raise ValueError("issue title must contain between 8 and 120 characters")
        if len(description) < 20:
            raise ValueError("issue description must contain at least 20 characters")
        if reason not in self.DISCOVERY_REASONS:
            raise ValueError("issue durable_reason is not admissible")
        if not isinstance(acceptance, list) or not acceptance:
            raise ValueError("issue acceptance_criteria must be a non-empty array")
        acceptance = [str(item).strip() for item in acceptance]
        if any(not item for item in acceptance):
            raise ValueError("issue acceptance criteria must be non-empty")
        if not check:
            raise ValueError("issue reproducible_check must be non-empty")
        fingerprint = self._title_fingerprint(title)
        if fingerprint in title_ids:
            raise ValueError(f"duplicate title matches {title_ids[fingerprint]}")
        issue_type = str(discovery.get("issue_type") or "task").strip()
        if issue_type not in {"bug", "feature", "task", "chore"}:
            raise ValueError("issue_type must be bug, feature, task, or chore")
        raw_priority = discovery.get("priority", 2)
        try:
            priority = int(str(raw_priority).upper().removeprefix("P"))
        except ValueError as exc:
            raise ValueError("priority must be between 0 and 4") from exc
        if priority < 0 or priority > 4:
            raise ValueError("priority must be between 0 and 4")
        evidence_text = "\n".join(
            f"- {item['type']} {item['source']}: {item['observation']}"
            for item in evidence
        )
        completed = self._run(
            workspace,
            [
                "bd",
                "create",
                title,
                "--description",
                (
                    f"{description}\n\nDurable reason: {reason}\n"
                    f"Reproducible check: {check}\nEvidence:\n{evidence_text}"
                )[:12_000],
                "--acceptance",
                "\n".join(f"- {item}" for item in acceptance)[:12_000],
                "--type",
                issue_type,
                "--priority",
                str(priority),
                "--labels",
                "orchestrator-discovery,evidence-admitted",
                "--deps",
                f"discovered-from:{source_issue_id}",
                "--silent",
            ],
        )
        issue_id = completed.stdout.strip().splitlines()[-1]
        self._validate_issue_id(issue_id)
        title_ids[fingerprint] = issue_id
        return {
            "kind": "issue",
            "issue_id": issue_id,
            "title": title,
            "durable_reason": reason,
        }

    def _admit_dependency(
        self,
        workspace: Path,
        discovery: dict[str, Any],
    ) -> dict[str, Any]:
        issue_id = str(discovery.get("issue_id") or "").strip()
        depends_on_id = str(discovery.get("depends_on_id") or "").strip()
        confidence = str(discovery.get("confidence") or "").strip()
        blocked_criterion = str(discovery.get("blocked_criterion") or "").strip()
        check = str(discovery.get("reproducible_check") or "").strip()
        evidence = self._validated_discovery_evidence(discovery.get("evidence"))
        self._validate_issue_id(issue_id)
        self._validate_issue_id(depends_on_id)
        if issue_id == depends_on_id:
            raise ValueError("dependency cannot reference itself")
        if confidence != "high":
            raise ValueError("dependency confidence must be high")
        if not blocked_criterion:
            raise ValueError("dependency blocked_criterion must be non-empty")
        if not check:
            raise ValueError("dependency reproducible_check must be non-empty")
        snapshot = self.snapshot(workspace, issue_id)
        self.snapshot(workspace, depends_on_id)
        dependencies = snapshot.get("dependencies")
        if isinstance(dependencies, list) and any(
            isinstance(item, dict)
            and item.get("id") == depends_on_id
            and item.get("dependency_type") == "blocks"
            for item in dependencies
        ):
            raise ValueError("dependency edge already exists")
        self._run(workspace, ["bd", "dep", "add", issue_id, depends_on_id])
        evidence_text = "; ".join(
            f"{item['type']} {item['source']}: {item['observation']}"
            for item in evidence
        )
        self.comment(
            workspace,
            issue_id,
            (
                f"Evidence-gated dependency admitted: {issue_id} depends on "
                f"{depends_on_id}\nBlocked criterion: {blocked_criterion}\n"
                f"Reproducible check: {check}\nEvidence: {evidence_text}"
            )[:8_000],
        )
        return {
            "kind": "dependency",
            "edge": f"{issue_id}->{depends_on_id}",
            "issue_id": issue_id,
            "depends_on_id": depends_on_id,
        }

    @classmethod
    def _validated_discovery_evidence(cls, value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list) or not value:
            raise ValueError("discovery evidence must be a non-empty array")
        evidence: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("each discovery evidence item must be an object")
            evidence_type = str(item.get("type") or "").strip()
            source = str(item.get("source") or "").strip()
            observation = str(item.get("observation") or "").strip()
            if evidence_type not in cls.EVIDENCE_TYPES:
                raise ValueError("discovery evidence type is not admissible")
            if not source or len(observation) < 10:
                raise ValueError(
                    "discovery evidence needs a source and concrete observation"
                )
            evidence.append(
                {
                    "type": evidence_type,
                    "source": source[:1_000],
                    "observation": observation[:4_000],
                }
            )
        return evidence

    @staticmethod
    def _title_fingerprint(title: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()

    def _prepare_locked(
        self,
        workspace: Path,
        beads_root: Path,
        task: str,
        acceptance_criteria: list[str],
        issue_id: str | None,
    ) -> dict[str, Any]:
        candidate_counts = {"in_progress": 0, "ready": 0}
        selection = "explicit"
        snapshot: dict[str, Any]
        if issue_id is not None:
            self._validate_issue_id(issue_id)
            snapshot = self.snapshot(workspace, issue_id)
            if snapshot.get("status") not in {"open", "in_progress"}:
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
            selection = (
                "resumed-explicit"
                if snapshot.get("status") == "in_progress"
                else "claimed-explicit"
            )
            if not self._acquire_issue_lease(beads_root, issue_id):
                return {
                    "enabled": True,
                    "launch_allowed": False,
                    "issue_id": issue_id,
                    "snapshot": snapshot,
                    "reason": (
                        "Bead already has an active Orchestrator workflow in "
                        "another live client; resume that workflow instead"
                    ),
                }
        else:
            candidates, candidate_counts = self._selection_candidates(workspace)
            selected = None
            active_issue_ids: list[str] = []
            for candidate in self.rank_candidates(candidates):
                candidate_id = str(candidate.get("id") or "")
                self._validate_issue_id(candidate_id)
                if self._acquire_issue_lease(beads_root, candidate_id):
                    selected = candidate
                    break
                active_issue_ids.append(candidate_id)
            if selected is not None:
                issue_id = str(selected["id"])
                snapshot = self.snapshot(workspace, issue_id)
                selection = (
                    "resumed-in-progress"
                    if snapshot.get("status") == "in_progress"
                    else "claimed-ready"
                )
            elif candidates:
                return {
                    "enabled": True,
                    "launch_allowed": False,
                    "selection": "all-candidates-active",
                    "candidate_counts": candidate_counts,
                    "active_issue_ids": active_issue_ids,
                    "reason": (
                        "Every resumable or dependency-ready Bead already has "
                        "an active Orchestrator workflow"
                    ),
                }
            else:
                if self.CONTINUATION.search(task):
                    return {
                        "enabled": True,
                        "launch_allowed": False,
                        "selection": "queue-empty",
                        "candidate_counts": candidate_counts,
                        "reason": (
                            "No in-progress or dependency-ready Bead remains; "
                            "continuation is complete"
                        ),
                    }
                issue_id = self._create_issue(
                    workspace, task, acceptance_criteria
                )
                if not self._acquire_issue_lease(beads_root, issue_id):
                    raise BeadsError(
                        f"newly created Bead could not be leased: {issue_id}"
                    )
                snapshot = self.snapshot(workspace, issue_id)
                selection = "created"
        assert issue_id is not None
        try:
            if snapshot.get("status") == "open":
                self._run(workspace, ["bd", "update", issue_id, "--claim"])
                snapshot = self.snapshot(workspace, issue_id)
        except Exception:
            self._release_issue_lease(beads_root, issue_id)
            raise
        resolved_acceptance = self._resolved_acceptance(
            snapshot, acceptance_criteria
        )
        return {
            "enabled": True,
            "launch_allowed": True,
            "issue_id": issue_id,
            "selection": selection,
            "candidate_counts": candidate_counts,
            "resolved_task": self._resolved_task(task, snapshot),
            "resolved_acceptance_criteria": resolved_acceptance,
            "snapshot": snapshot,
        }

    def _create_issue(
        self,
        workspace: Path,
        task: str,
        acceptance_criteria: list[str],
    ) -> str:
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
        return issue_id

    def _selection_candidates(
        self, workspace: Path
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        in_progress = self._list_issues(
            workspace,
            ["bd", "list", "--status", "in_progress", "--json", "--limit", "0"],
        )
        ready = self._list_issues(workspace, ["bd", "ready", "--json"])
        return (
            [*in_progress, *ready],
            {"in_progress": len(in_progress), "ready": len(ready)},
        )

    def _list_issues(
        self, workspace: Path, argv: list[str]
    ) -> list[dict[str, Any]]:
        completed = self._run(workspace, argv)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise BeadsError(f"{' '.join(argv[:2])} returned invalid JSON") from exc
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            raise BeadsError(f"{' '.join(argv[:2])} returned a non-list payload")
        return payload

    @classmethod
    def rank_candidates(
        cls, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return sorted(candidates, key=cls._candidate_key)

    @classmethod
    def _candidate_key(cls, candidate: dict[str, Any]) -> tuple[Any, ...]:
        status_order = 0 if candidate.get("status") == "in_progress" else 1
        raw_priority = str(candidate.get("priority", 4)).upper().removeprefix("P")
        try:
            priority = int(raw_priority)
        except ValueError:
            priority = 4
        updated_at = cls._timestamp(candidate.get("updated_at"))
        return (
            status_order,
            priority,
            -updated_at,
            str(candidate.get("id") or ""),
        )

    @staticmethod
    def _timestamp(value: Any) -> float:
        if not isinstance(value, str) or not value:
            return 0.0
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0

    @staticmethod
    def _resolved_task(task: str, snapshot: dict[str, Any]) -> str:
        parts = [
            f"Continue Bead {snapshot.get('id')}: {snapshot.get('title', 'Untitled')}",
            f"Operator instruction: {task.strip() or 'continue'}",
        ]
        for label, field in (
            ("Description", "description"),
            ("Design", "design"),
            ("Notes", "notes"),
        ):
            value = snapshot.get(field)
            if value:
                parts.append(f"{label}:\n{value}")
        acceptance = snapshot.get("acceptance_criteria")
        if acceptance:
            parts.append(f"Acceptance criteria:\n{acceptance}")
        return "\n\n".join(parts)[:24_000]

    @staticmethod
    def _resolved_acceptance(
        snapshot: dict[str, Any], supplied: list[str]
    ) -> list[str]:
        values: list[str] = []
        raw = snapshot.get("acceptance_criteria")
        if isinstance(raw, list):
            values.extend(str(item).strip() for item in raw)
        elif isinstance(raw, str):
            lines = [line.strip() for line in raw.splitlines() if line.strip()]
            values.extend(line.removeprefix("-").strip() for line in lines)
        values.extend(item.strip() for item in supplied)
        return list(dict.fromkeys(item for item in values if item))

    @classmethod
    def _frontier_candidate(
        cls, candidate: dict[str, Any]
    ) -> dict[str, Any]:
        dependencies = candidate.get("dependencies")
        dependents = candidate.get("dependents")
        bounded: dict[str, Any] = {}
        for field in (
            "id",
            "title",
            "status",
            "priority",
            "issue_type",
            "assignee",
            "updated_at",
        ):
            value = candidate.get(field)
            if value not in (None, "", [], {}):
                bounded[field] = value
        for field in ("description", "acceptance_criteria"):
            value = candidate.get(field)
            if isinstance(value, str) and value:
                bounded[field] = value[:4_000]
            elif isinstance(value, list):
                bounded[field] = [str(item)[:1_000] for item in value[:20]]
        if isinstance(dependencies, list):
            bounded["dependencies"] = dependencies[:20]
            bounded["dependency_count"] = len(dependencies)
        else:
            bounded["dependency_count"] = 0
        if isinstance(dependents, list):
            bounded["dependent_count"] = len(dependents)
        else:
            bounded["dependent_count"] = 0
        return bounded

    @contextmanager
    def _workspace_lock(self, beads_root: Path) -> Iterator[None]:
        lock_path = beads_root / ".beads" / "orchestrator-intake.lock"
        handle = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def _acquire_issue_lease(self, beads_root: Path, issue_id: str) -> bool:
        key = (beads_root, issue_id)
        if key in self._leases:
            return False
        lock_path = beads_root / ".beads" / f"orchestrator-{issue_id}.lock"
        handle = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        self._leases[key] = handle
        return True

    def _release_issue_lease(self, beads_root: Path, issue_id: str) -> None:
        handle = self._leases.pop((beads_root, issue_id), None)
        if handle is None:
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()

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
        workspace = workspace.expanduser().resolve()
        beads_root = self._beads_root(workspace)
        if beads_root is None:
            raise BeadsError(f"no .beads directory under {workspace}")
        try:
            with self._workspace_lock(beads_root):
                completed_units = sum(
                    1
                    for item in queue
                    if str(item.get("status"))
                    in {"returned", "verified", "accepted"}
                )
                recovery_attempts = []
                for item in queue:
                    unit_id = str(item.get("id") or "unknown-unit")
                    attempts = item.get("routeAttempts")
                    if not isinstance(attempts, list):
                        continue
                    for attempt in attempts:
                        if not isinstance(attempt, dict):
                            continue
                        outcome = str(attempt.get("outcome") or "")
                        model = str(attempt.get("model") or "unknown-model")
                        reasons = attempt.get("reasons")
                        rendered_reasons = (
                            "; ".join(str(reason) for reason in reasons)
                            if isinstance(reasons, list)
                            else "no reason recorded"
                        )
                        recovery_attempts.append(
                            (
                                unit_id,
                                outcome,
                                f"- {unit_id} via {model}: {outcome} - "
                                f"{rendered_reasons[:500]}"
                            )
                        )
                fallback_units = {
                    unit_id
                    for unit_id, _, _ in recovery_attempts
                    if sum(
                        1
                        for candidate_id, _, _ in recovery_attempts
                        if candidate_id == unit_id
                    ) > 1
                }
                rendered_attempts = [
                    line
                    for unit_id, outcome, line in recovery_attempts
                    if unit_id in fallback_units or outcome != "usable"
                ]
                quality_history = (
                    "\n- Recovery attempts:\n"
                    + "\n".join(rendered_attempts[:20])
                    if rendered_attempts
                    else "\n- Recovery attempts: none"
                )
                comment = (
                    "Claude native workflow checkpoint\n\n"
                    f"- Decision: {decision}\n"
                    f"- Stop reason: {stop_reason or 'none'}\n"
                    f"- Queue: {completed_units}/{len(queue)} units returned or verified\n"
                    f"- Summary: {summary.strip()[:8_000] or 'No summary returned.'}"
                    f"{quality_history}"
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
                    self._run(
                        workspace,
                        ["bd", "update", issue_id, "--status", "blocked"],
                    )
                    status = "blocked"
                else:
                    status = "in_progress"
        finally:
            self._release_issue_lease(beads_root, issue_id)
        return {"enabled": True, "issue_id": issue_id, "status": status}

    def validate_checkpoint_target(
        self,
        workspace: Path,
        issue_id: str,
    ) -> None:
        """Fail before persistence when the Beads checkpoint target is invalid."""
        self._validate_issue_id(issue_id)
        workspace = workspace.expanduser().resolve()
        if self._beads_root(workspace) is None:
            raise BeadsError(f"no .beads directory under {workspace}")
        self.snapshot(workspace, issue_id)

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
            "owner",
            "assignee",
            "labels",
            "created_at",
            "updated_at",
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
        command = list(argv)
        if command and command[0] == "bd":
            command[0] = resolve_bd_binary() or "bd"
        for attempt in range(5):
            try:
                completed = subprocess.run(
                    command,
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
            if completed.returncode == 0:
                return completed
            detail = (completed.stderr or completed.stdout).strip()
            lock_conflict = (
                "another process holds the exclusive lock" in detail
                or "database is locked" in detail
            )
            if lock_conflict and attempt < 4:
                time.sleep(0.1 * (2**attempt))
                continue
            raise BeadsError(f"{' '.join(command[:3])} failed: {detail}")
        raise BeadsError(f"{' '.join(command[:3])} failed after retries")
