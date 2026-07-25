from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from orchestrator.config import AppConfig


class ConfigTests(unittest.TestCase):
    def test_installed_cli_discovers_the_central_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ORCHESTRATOR_ROOT", None)
                with patch("orchestrator.config.Path.cwd", return_value=Path(directory)):
                    config = AppConfig.load()

        self.assertEqual(config.root, Path.home() / "Documents" / "orchestrator")

    def test_product_config_is_consistent(self) -> None:
        config = AppConfig.load()
        self.assertEqual(len(config.personas), 6)
        self.assertEqual(
            set(config.models),
            {
                "opus-5[1m]",
                "opus-5-bounded",
                "opus-4.8-bounded",
                "fable-5[1m]",
                "fable-5-bounded",
                "gpt-5.6-sol",
                "codex-sol-high",
                "codex-sol-medium",
            },
        )
        self.assertEqual(config.models["codex-sol-high"].reasoning_effort, "high")
        preferred = {
            model
            for persona in config.personas.values()
            for model in persona.preferred_models
        }
        self.assertLessEqual(preferred, set(config.models))
        self.assertEqual(config.models["gpt-5.6-sol"].family, "openai")
        self.assertEqual(config.models["gpt-5.6-sol"].context_window, 272_000)
        self.assertEqual(config.models["codex-sol-high"].model, "gpt-5.6-sol")
        self.assertEqual(config.models["codex-sol-medium"].model, "gpt-5.6-sol")
        self.assertEqual(config.models["opus-5-bounded"].context_window, 1_000_000)
        self.assertEqual(config.team_policy.routing_mode, "shadow")
        self.assertEqual(
            config.profile_source_warnings(today=date(2026, 7, 25)),
            (),
        )
        self.assertTrue(config.models["opus-4.8-bounded"].fallback_only)
        self.assertEqual(
            config.models["opus-4.8-bounded"].model,
            "claude-opus-4-8",
        )
        self.assertEqual(
            config.personas["exploiter"].preferred_models,
            ("opus-5-bounded", "codex-sol-high", "opus-4.8-bounded"),
        )
        self.assertEqual(
            config.personas["challenger"].preferred_models,
            ("opus-5-bounded", "codex-sol-medium", "opus-4.8-bounded"),
        )
        self.assertEqual(
            config.personas["engineer"].preferred_models,
            ("opus-5-bounded", "codex-sol-high", "opus-4.8-bounded"),
        )
        self.assertEqual(
            config.personas["verifier"].preferred_models,
            (
                "fable-5-bounded",
                "opus-5-bounded",
                "gpt-5.6-sol",
                "opus-4.8-bounded",
            ),
        )
        self.assertEqual(
            config.personas["judge"].preferred_models,
            (
                "fable-5-bounded",
                "opus-5-bounded",
                "gpt-5.6-sol",
                "opus-4.8-bounded",
            ),
        )
        self.assertGreater(config.models["gpt-5.6-sol"].traits["verification"], 0.0)
        self.assertGreater(config.personas["judge"].trait_weights["skepticism"], 0.0)
        self.assertEqual(
            config.team_policy.security_neutral_routes["fable-5-bounded"],
            (),
        )
        self.assertIn("exploit", config.team_policy.security_task_keywords)
        workflow = config.workflow("security-research-forum")
        self.assertTrue(workflow.requires_authorization)
        self.assertEqual(workflow.max_rounds, 6)
        self.assertEqual(
            workflow.stages[0].personas,
            (
                "researcher",
                "challenger",
                "exploiter",
                "engineer",
                "verifier",
                "judge",
            ),
        )
        general = config.workflow("general-forum")
        self.assertFalse(general.requires_authorization)
        self.assertIn("exploiter", general.stages[0].personas)

    def test_profile_source_warnings_flag_undated_and_stale_profiles(self) -> None:
        config = AppConfig.load()
        models = dict(config.models)
        models["opus-5-bounded"] = replace(
            models["opus-5-bounded"],
            profile_source="manual-anecdote",
        )
        models["codex-sol-high"] = replace(
            models["codex-sol-high"],
            profile_source="live-route-2026-05-01",
        )

        warnings = replace(config, models=models).profile_source_warnings(
            today=date(2026, 7, 25),
        )

        self.assertTrue(any("opus-5-bounded" in item and "undated" in item for item in warnings))
        self.assertTrue(any("codex-sol-high" in item and "stale" in item for item in warnings))


if __name__ == "__main__":
    unittest.main()
