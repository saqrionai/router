from __future__ import annotations

import unittest

from orchestrator.composer import TeamComposer
from orchestrator.config import AppConfig


class ComposerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AppConfig.load()
        self.composer = TeamComposer(
            models=self.config.models,
            personas=self.config.personas,
            policy=self.config.team_policy,
        )
        self.workflow = self.config.workflow("security-research-forum")

    def test_composes_complementary_independent_team(self) -> None:
        plan = self.composer.compose(
            self.workflow,
            "reverse engineering firmware exploit research with large context",
        )
        selected = {
            assignment.persona: assignment.model for assignment in plan.assignments
        }

        self.assertEqual(len(plan.assignments), 6)
        self.assertEqual(plan.unique_models, 3)
        self.assertEqual(plan.unique_families, 2)
        self.assertEqual(selected["researcher"], "opus-5-bounded")
        self.assertEqual(selected["bullshitter"], "opus-5-bounded")
        self.assertEqual(selected["exploiter"], "opus-5-bounded")
        self.assertEqual(selected["engineer"], "gpt-5.6-high")
        self.assertEqual(selected["verifier"], "opus-5-bounded")
        self.assertEqual(selected["judge"], "gpt-5.6-sol")
        self.assertNotEqual(
            self.config.models[selected["engineer"]].family,
            self.config.models[selected["verifier"]].family,
        )
        self.assertNotEqual(
            self.config.models[selected["exploiter"]].family,
            self.config.models[selected["judge"]].family,
        )
        for persona_id in ("bullshitter", "exploiter", "engineer"):
            assignment = plan.assignment_for(persona_id)
            self.assertNotIn("fable-5-bounded", assignment.fallback_order)
        for assignment in plan.assignments:
            self.assertNotEqual(assignment.model, "opus-4.8-bounded")
            self.assertEqual(
                assignment.fallback_order[1],
                "opus-4.8-bounded",
            )

    def test_selected_model_leads_fallback_order(self) -> None:
        plan = self.composer.compose(self.workflow, "implement and debug code")
        for assignment in plan.assignments:
            self.assertEqual(assignment.fallback_order[0], assignment.model)
            self.assertEqual(
                set(assignment.fallback_order),
                {
                    model_id
                    for model_id in self.config.personas[
                        assignment.persona
                    ].preferred_models
                    if model_id != "fable-5-bounded"
                },
            )

    def test_authorization_required_workflow_excludes_fable_for_neutral_text(
        self,
    ) -> None:
        plan = self.composer.compose(
            self.workflow,
            "compare my patch with the maintainer patch",
        )

        for assignment in plan.assignments:
            self.assertNotEqual(assignment.model, "fable-5-bounded")
            self.assertNotIn("fable-5-bounded", assignment.fallback_order)

    def test_general_workflow_keeps_fable_available_for_non_security_work(
        self,
    ) -> None:
        workflow = self.config.workflow("general-forum")
        plan = self.composer.compose(
            workflow,
            "review this product proposal and verify every claim",
        )

        verifier = plan.assignment_for("verifier")
        self.assertEqual(verifier.model, "fable-5-bounded")
        self.assertIn("fable-5-bounded", verifier.fallback_order)

    def test_task_signals_are_explainable(self) -> None:
        plan = self.composer.compose(
            self.workflow, "reverse engineering firmware with large context"
        )
        self.assertGreater(plan.task_traits["context_endurance"], 0.0)
        self.assertGreater(plan.task_traits["security_reasoning"], 0.0)

    def test_low_confidence_profiles_are_shrunk_toward_neutral(self) -> None:
        model = self.config.models["opus-5[1m]"]
        raw = model.traits["research"]
        effective = self.composer._effective_trait(model, "research")

        self.assertGreater(raw, effective)
        self.assertGreater(effective, 0.5)

    def test_applies_learned_route_adjustments(self) -> None:
        baseline = self.composer.compose(
            self.workflow, "research and verify a codebase"
        )
        adjusted = TeamComposer(
            models=self.config.models,
            personas=self.config.personas,
            policy=self.config.team_policy,
            route_adjustments={("researcher", "gpt-5.6-research"): 10.0},
        ).compose(self.workflow, "research and verify a codebase")

        baseline_models = {
            assignment.persona: assignment.model
            for assignment in baseline.assignments
        }
        adjusted_models = {
            assignment.persona: assignment.model
            for assignment in adjusted.assignments
        }
        self.assertEqual(
            adjusted_models["researcher"], "gpt-5.6-research"
        )
        self.assertNotEqual(
            adjusted_models["researcher"], baseline_models["researcher"]
        )
        researcher = adjusted.assignment_for("researcher")
        self.assertIn("learned-route=+10.000", researcher.reasons)


if __name__ == "__main__":
    unittest.main()
