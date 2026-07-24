from __future__ import annotations

import os
import tempfile
import unittest
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
                "fable-5[1m]",
                "fable-5-bounded",
                "gpt-5.6-sol",
                "gpt-5.6-high",
                "gpt-5.6-research",
            },
        )
        self.assertEqual(config.models["gpt-5.6-high"].reasoning_effort, "high")
        preferred = {
            model
            for persona in config.personas.values()
            for model in persona.preferred_models
        }
        self.assertLessEqual(preferred, set(config.models))
        self.assertEqual(config.models["gpt-5.6-sol"].family, "openai")
        self.assertEqual(config.models["gpt-5.6-sol"].context_window, 1_050_000)
        self.assertEqual(config.models["opus-5-bounded"].context_window, 1_000_000)
        self.assertEqual(
            config.personas["exploiter"].preferred_models,
            ("opus-5-bounded", "gpt-5.6-high"),
        )
        self.assertEqual(
            config.personas["bullshitter"].preferred_models,
            ("opus-5-bounded", "gpt-5.6-research"),
        )
        self.assertEqual(
            config.personas["engineer"].preferred_models,
            ("opus-5-bounded", "gpt-5.6-high"),
        )
        self.assertEqual(
            config.personas["verifier"].preferred_models,
            ("fable-5-bounded", "opus-5-bounded", "gpt-5.6-sol"),
        )
        self.assertEqual(
            config.personas["judge"].preferred_models,
            ("fable-5-bounded", "opus-5-bounded", "gpt-5.6-sol"),
        )
        self.assertGreater(config.models["gpt-5.6-sol"].traits["verification"], 0.0)
        self.assertGreater(config.personas["judge"].trait_weights["skepticism"], 0.0)
        self.assertEqual(
            config.team_policy.security_neutral_routes["fable-5-bounded"],
            ("researcher", "verifier", "judge"),
        )
        self.assertIn("exploit", config.team_policy.security_task_keywords)
        workflow = config.workflow("security-research-forum")
        self.assertTrue(workflow.requires_authorization)
        self.assertEqual(workflow.max_rounds, 6)
        self.assertEqual(
            workflow.stages[0].personas,
            (
                "researcher",
                "bullshitter",
                "exploiter",
                "engineer",
                "verifier",
                "judge",
            ),
        )


if __name__ == "__main__":
    unittest.main()
