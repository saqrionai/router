from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.beads import BeadsBridge


class BeadsBridgeTests(unittest.TestCase):
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

    @patch("orchestrator.beads.subprocess.run")
    def test_comment_is_append_only(self, run) -> None:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")

        BeadsBridge().comment(Path("/tmp/project"), "ios-123", "run summary")

        self.assertEqual(
            run.call_args.args[0],
            ["bd", "comments", "add", "ios-123", "run summary"],
        )
