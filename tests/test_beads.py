from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.beads import BeadsBridge


class BeadsBridgeTests(unittest.TestCase):
    def test_candidates_prefer_in_progress_then_priority_then_recency(self) -> None:
        candidates = [
            {
                "id": "ios-ready-p0",
                "status": "open",
                "priority": 0,
                "updated_at": "2026-07-24T16:00:00Z",
            },
            {
                "id": "ios-active-p1-old",
                "status": "in_progress",
                "priority": "P1",
                "updated_at": "2026-07-23T16:00:00Z",
            },
            {
                "id": "ios-active-p1-new",
                "status": "in_progress",
                "priority": 1,
                "updated_at": "2026-07-24T16:00:00Z",
            },
        ]

        ranked = BeadsBridge.rank_candidates(candidates)

        self.assertEqual(
            [item["id"] for item in ranked],
            ["ios-active-p1-new", "ios-active-p1-old", "ios-ready-p0"],
        )

    def test_resolved_task_hydrates_continue_from_bead(self) -> None:
        snapshot = {
            "id": "ios-123",
            "title": "Automate boot ROM",
            "description": "Continue the verified USB state machine.",
            "acceptance_criteria": "- cold boot passes\n- reconnect passes",
        }

        task = BeadsBridge._resolved_task("continue", snapshot)
        acceptance = BeadsBridge._resolved_acceptance(snapshot, [])

        self.assertIn("Continue Bead ios-123: Automate boot ROM", task)
        self.assertIn("Continue the verified USB state machine.", task)
        self.assertEqual(acceptance, ["cold boot passes", "reconnect passes"])

    def test_issue_lease_prevents_duplicate_live_client(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".beads").mkdir()
            first = BeadsBridge()
            second = BeadsBridge()

            self.assertTrue(first._acquire_issue_lease(root, "ios-123"))
            self.assertFalse(second._acquire_issue_lease(root, "ios-123"))
            first._release_issue_lease(root, "ios-123")
            self.assertTrue(second._acquire_issue_lease(root, "ios-123"))
            second._release_issue_lease(root, "ios-123")

    @patch("orchestrator.beads.subprocess.run")
    def test_snapshot_is_bounded_and_uses_workspace(self, run) -> None:
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "id": "ios-123",
                        "title": "Boot automation",
                        "status": "in_progress",
                        "description": "x" * 13_000,
                        "private_field": "not copied",
                    }
                ]
            ),
            stderr="",
        )

        snapshot = BeadsBridge().snapshot(Path("/tmp/project"), "ios-123")

        self.assertEqual(snapshot["id"], "ios-123")
        self.assertIn("[truncated by Orchestrator]", snapshot["description"])
        self.assertNotIn("private_field", snapshot)
        self.assertEqual(run.call_args.kwargs["cwd"], Path("/tmp/project"))

    @patch.dict(os.environ, {"ORCHESTRATOR_BD_BIN": ""})
    @patch("orchestrator.beads.subprocess.run")
    def test_comment_is_append_only(self, run) -> None:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")

        BeadsBridge().comment(Path("/tmp/project"), "ios-123", "run summary")

        self.assertEqual(
            run.call_args.args[0],
            ["bd", "comments", "add", "ios-123", "run summary"],
        )

    @patch.dict(
        os.environ,
        {"ORCHESTRATOR_BD_BIN": "/opt/homebrew/bin/bd"},
    )
    @patch("orchestrator.beads.subprocess.run")
    def test_configured_bd_binary_replaces_path_lookup(self, run) -> None:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")

        BeadsBridge().comment(Path("/tmp/project"), "ios-123", "run summary")

        self.assertEqual(
            run.call_args.args[0],
            [
                "/opt/homebrew/bin/bd",
                "comments",
                "add",
                "ios-123",
                "run summary",
            ],
        )
