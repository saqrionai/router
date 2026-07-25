from __future__ import annotations

import itertools
from collections import Counter

from orchestrator.domain import (
    ModelRoute,
    Persona,
    TeamAssignment,
    TeamPlan,
    TeamPolicy,
    Workflow,
)
from orchestrator.eligibility import is_route_eligible


class TeamComposer:
    """Select a complementary model slate from calibrated behavioral priors."""

    def __init__(
        self,
        *,
        models: dict[str, ModelRoute],
        personas: dict[str, Persona],
        policy: TeamPolicy,
        route_adjustments: dict[tuple[str, str], float] | None = None,
    ):
        self.models = models
        self.personas = personas
        self.policy = policy
        self.route_adjustments = route_adjustments or {}

    def compose(self, workflow: Workflow, task: str = "") -> TeamPlan:
        persona_ids = self._workflow_personas(workflow)
        task_traits = self._task_traits(task)
        eligibility_task = (
            f"security {task}" if workflow.requires_authorization else task
        )
        candidates = [
            tuple(
                model_id
                for model_id in self.personas[persona_id].preferred_models
                if not self.models[model_id].fallback_only
                if is_route_eligible(
                    task=eligibility_task,
                    persona_id=persona_id,
                    model_id=model_id,
                    policy=self.policy,
                )
            )
            for persona_id in persona_ids
        ]
        unavailable = [
            persona_id
            for persona_id, model_ids in zip(persona_ids, candidates, strict=True)
            if not model_ids
        ]
        if unavailable:
            raise ValueError(
                f"workflow {workflow.id!r} has no eligible routes for {unavailable}"
            )
        best_models: tuple[str, ...] | None = None
        best_score = float("-inf")

        for model_ids in itertools.product(*candidates):
            score = self._team_score(persona_ids, model_ids, task_traits)
            # The tuple tie-break makes composition deterministic across Python runs.
            tie_break = tuple(model_ids)
            if score > best_score or (
                score == best_score
                and best_models is not None
                and tie_break < tuple(best_models)
            ):
                best_score = score
                best_models = tuple(model_ids)

        if best_models is None:
            raise ValueError(f"workflow {workflow.id!r} has no model candidates")

        assignments = tuple(
            self._assignment(
                persona_id,
                model_id,
                eligibility_task,
                task_traits,
            )
            for persona_id, model_id in zip(persona_ids, best_models, strict=True)
        )
        families = {self.models[model_id].family for model_id in best_models}
        return TeamPlan(
            assignments=assignments,
            total_score=round(best_score, 6),
            unique_models=len(set(best_models)),
            unique_families=len(families),
            task_traits=task_traits,
        )

    def _workflow_personas(self, workflow: Workflow) -> tuple[str, ...]:
        ordered: list[str] = []
        for stage in workflow.stages:
            for persona in stage.personas:
                if persona not in ordered:
                    ordered.append(persona)
        return tuple(ordered)

    def _task_traits(self, task: str) -> dict[str, float]:
        lower = task.lower()
        totals: Counter[str] = Counter()
        for keyword, boosts in self.policy.task_signals.items():
            if keyword.lower() in lower:
                totals.update(boosts)
        return {name: min(value, 1.0) for name, value in sorted(totals.items())}

    def _role_score(
        self,
        persona: Persona,
        model: ModelRoute,
        task_traits: dict[str, float],
    ) -> float:
        weight_total = sum(abs(value) for value in persona.trait_weights.values()) or 1.0
        trait_fit = sum(
            weight * self._effective_trait(model, trait)
            for trait, weight in persona.trait_weights.items()
        ) / weight_total
        required_fit = 0.0
        if persona.required_strengths:
            required_fit = sum(
                1.0 for strength in persona.required_strengths if strength in model.strengths
            ) / len(persona.required_strengths)
        task_fit = 0.0
        if task_traits:
            task_fit = sum(
                weight * self._effective_trait(model, trait)
                for trait, weight in task_traits.items()
            ) / sum(task_traits.values())
        primary_preferences = tuple(
            model_id
            for model_id in persona.preferred_models
            if not self.models[model_id].fallback_only
        )
        rank = primary_preferences.index(model.id)
        preference = (len(primary_preferences) - rank) / len(
            primary_preferences
        )
        behavioral_fit = 0.7 * trait_fit + 0.2 * required_fit + 0.1 * task_fit
        return (
            self.policy.role_fit_weight * behavioral_fit
            + self.policy.preference_weight * preference
            + self.policy.family_budget_bias.get(model.family, 0.0)
            + self.route_adjustments.get((persona.id, model.id), 0.0)
        )

    @staticmethod
    def _effective_trait(model: ModelRoute, trait: str) -> float:
        """Shrink uncertain behavioral priors toward a neutral score."""
        raw = model.traits.get(trait, 0.5)
        return 0.5 + model.profile_confidence * (raw - 0.5)

    def _team_score(
        self,
        persona_ids: tuple[str, ...],
        model_ids: tuple[str, ...],
        task_traits: dict[str, float],
    ) -> float:
        score = sum(
            self._role_score(
                self.personas[persona_id], self.models[model_id], task_traits
            )
            for persona_id, model_id in zip(persona_ids, model_ids, strict=True)
        )
        model_counts = Counter(model_ids)
        family_counts = Counter(self.models[model_id].family for model_id in model_ids)
        score += self.policy.unique_model_bonus * len(model_counts)
        score += self.policy.unique_family_bonus * len(family_counts)
        score -= self.policy.duplicate_model_penalty * sum(
            count - 1 for count in model_counts.values() if count > 1
        )
        score -= self.policy.duplicate_family_penalty * sum(
            count - 1 for count in family_counts.values() if count > 1
        )

        selected = dict(zip(persona_ids, model_ids, strict=True))
        for left, right in self.policy.independence_pairs:
            if left not in selected or right not in selected:
                continue
            left_model = self.models[selected[left]]
            right_model = self.models[selected[right]]
            if left_model.id == right_model.id:
                score -= self.policy.independence_model_penalty
            elif left_model.family == right_model.family:
                score -= self.policy.independence_family_penalty
        return score

    def _assignment(
        self,
        persona_id: str,
        model_id: str,
        task: str,
        task_traits: dict[str, float],
    ) -> TeamAssignment:
        persona = self.personas[persona_id]
        model = self.models[model_id]
        scored_traits = sorted(
            (
                (
                    weight * self._effective_trait(model, trait),
                    trait,
                    self._effective_trait(model, trait),
                )
                for trait, weight in persona.trait_weights.items()
            ),
            reverse=True,
        )
        reasons = [
            f"{trait}={value:.2f}" for _, trait, value in scored_traits[:3]
        ]
        reasons.append(f"style={','.join(model.styles[:3]) or 'uncalibrated'}")
        reasons.append(
            f"profile={model.profile_source}@{model.profile_confidence:.2f}"
        )
        budget_bias = self.policy.family_budget_bias.get(model.family, 0.0)
        if budget_bias:
            reasons.append(f"capacity-bias={budget_bias:+.2f}")
        route_adjustment = self.route_adjustments.get((persona_id, model_id), 0.0)
        if route_adjustment:
            reasons.append(f"learned-route={route_adjustment:+.3f}")
        eligible_fallbacks = tuple(
            candidate
            for candidate in persona.preferred_models
            if candidate != model_id
            and is_route_eligible(
                task=task,
                persona_id=persona_id,
                model_id=candidate,
                policy=self.policy,
            )
        )
        fallback_order = (
            (model_id,)
            + tuple(
                candidate
                for candidate in eligible_fallbacks
                if not self.models[candidate].fallback_only
            )
            + tuple(
                candidate
                for candidate in eligible_fallbacks
                if self.models[candidate].fallback_only
            )
        )
        return TeamAssignment(
            persona=persona_id,
            model=model_id,
            score=round(self._role_score(persona, model, task_traits), 6),
            reasons=tuple(reasons),
            fallback_order=fallback_order,
        )
