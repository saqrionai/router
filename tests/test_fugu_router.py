from __future__ import annotations

import unittest

from orchestrator.config import AppConfig
from orchestrator.fugu_router import FuguRouter


class FuguRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AppConfig.load()
        self.pool = (
            "opus-5-bounded",
            "gpt-5.6-high",
            "gpt-5.6-research",
        )

    def test_distribution_is_normalized_and_deterministic(self) -> None:
        router = FuguRouter(
            models=self.config.models,
            personas=self.config.personas,
            policy=self.config.team_policy,
        )

        first = router.rank(
            task="Implement and debug the repository code.",
            persona_id="engineer",
            model_ids=self.pool,
        )
        second = router.rank(
            task="Implement and debug the repository code.",
            persona_id="engineer",
            model_ids=self.pool,
        )

        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(item.probability for item in first), 1.0, places=5)
        self.assertEqual({item.model for item in first}, set(self.pool))

    def test_local_terminal_outcomes_shift_the_distribution(self) -> None:
        baseline = FuguRouter(
            models=self.config.models,
            personas=self.config.personas,
            policy=self.config.team_policy,
        ).rank(
            task="Implement a parser.",
            persona_id="engineer",
            model_ids=self.pool,
        )
        outcomes = [
            {
                "persona": "engineer",
                "model": "gpt-5.6-research",
                "calls": 20,
                "format_successes": 20,
                "terminal_calls": 20,
                "accepted_calls": 20,
            },
            {
                "persona": "engineer",
                "model": "gpt-5.6-high",
                "calls": 20,
                "format_successes": 20,
                "terminal_calls": 20,
                "accepted_calls": 0,
            },
        ]
        calibrated = FuguRouter(
            models=self.config.models,
            personas=self.config.personas,
            policy=self.config.team_policy,
            outcomes=outcomes,
        ).rank(
            task="Implement a parser.",
            persona_id="engineer",
            model_ids=self.pool,
        )

        baseline_probability = {
            candidate.model: candidate.probability for candidate in baseline
        }
        calibrated_probability = {
            candidate.model: candidate.probability for candidate in calibrated
        }
        self.assertGreater(
            calibrated_probability["gpt-5.6-research"],
            baseline_probability["gpt-5.6-research"],
        )
        self.assertLess(
            calibrated_probability["gpt-5.6-high"],
            baseline_probability["gpt-5.6-high"],
        )

    def test_duplicate_pool_is_rejected(self) -> None:
        router = FuguRouter(
            models=self.config.models,
            personas=self.config.personas,
            policy=self.config.team_policy,
        )

        with self.assertRaisesRegex(ValueError, "duplicate routes"):
            router.rank(
                task="Implement a parser.",
                persona_id="engineer",
                model_ids=("gpt-5.6-high", "gpt-5.6-high"),
            )

    def test_fable_is_excluded_from_security_tasks_after_native_fallback(self) -> None:
        router = FuguRouter(
            models=self.config.models,
            personas=self.config.personas,
            policy=self.config.team_policy,
        )
        pool = ("fable-5-bounded", "opus-5-bounded", "gpt-5.6-high")

        exploiter = router.rank(
            task="Analyze an authorized firmware exploit.",
            persona_id="exploiter",
            model_ids=pool,
        )
        verifier = router.rank(
            task="Verify evidence for an authorized firmware exploit.",
            persona_id="verifier",
            model_ids=pool,
        )

        self.assertNotIn("fable-5-bounded", {item.model for item in exploiter})
        self.assertNotIn("fable-5-bounded", {item.model for item in verifier})

    def test_malformed_outcome_counters_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "accepted calls"):
            FuguRouter(
                models=self.config.models,
                personas=self.config.personas,
                policy=self.config.team_policy,
                outcomes=[
                    {
                        "persona": "engineer",
                        "model": "gpt-5.6-high",
                        "calls": 1,
                        "format_successes": 1,
                        "terminal_calls": 0,
                        "accepted_calls": 1,
                    }
                ],
            )

    def test_retired_route_history_is_preserved_but_ignored(self) -> None:
        router = FuguRouter(
            models=self.config.models,
            personas=self.config.personas,
            policy=self.config.team_policy,
            outcomes=[
                {
                    "persona": "engineer",
                    "model": "retired-cloud-route",
                    "calls": 20,
                    "format_successes": 20,
                    "terminal_calls": 20,
                    "accepted_calls": 20,
                }
            ],
            observations=[
                {
                    "task": "Historical task",
                    "persona": "engineer",
                    "model": "retired-cloud-route",
                    "reward": 1.0,
                }
            ],
        )

        candidates = router.rank(
            task="Implement a parser.",
            persona_id="engineer",
            model_ids=self.pool,
        )

        self.assertTrue(candidates)
        self.assertTrue(all(candidate.calls == 0 for candidate in candidates))

    def test_contextual_head_learns_from_task_level_live_rewards(self) -> None:
        observations = []
        for index in range(20):
            observations.extend(
                [
                    {
                        "run_id": f"success-{index}",
                        "round": 1,
                        "task": "Implement and debug a binary protocol parser",
                        "persona": "engineer",
                        "model": "gpt-5.6-research",
                        "reward": 1.0,
                    },
                    {
                        "run_id": f"failure-{index}",
                        "round": 1,
                        "task": "Implement and debug a binary protocol parser",
                        "persona": "engineer",
                        "model": "gpt-5.6-high",
                        "reward": 0.0,
                    },
                ]
            )

        candidates = FuguRouter(
            models=self.config.models,
            personas=self.config.personas,
            policy=self.config.team_policy,
            observations=observations,
        ).rank(
            task="Implement and debug a binary protocol parser",
            persona_id="engineer",
            model_ids=self.pool,
        )
        by_model = {candidate.model: candidate for candidate in candidates}

        self.assertGreater(
            by_model["gpt-5.6-research"].contextual_success,
            by_model["gpt-5.6-high"].contextual_success,
        )
        self.assertEqual(
            by_model["gpt-5.6-research"].contextual_observations,
            20,
        )
        self.assertEqual(
            by_model["opus-5-bounded"].contextual_observations,
            0,
        )
        self.assertAlmostEqual(
            by_model["opus-5-bounded"].contextual_success,
            0.5,
        )

    def test_malformed_contextual_reward_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "reward must be within"):
            FuguRouter(
                models=self.config.models,
                personas=self.config.personas,
                policy=self.config.team_policy,
                observations=[
                    {
                        "task": "Implement a parser.",
                        "persona": "engineer",
                        "model": "gpt-5.6-high",
                        "reward": 2.0,
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
