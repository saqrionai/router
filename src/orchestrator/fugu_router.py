from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from orchestrator.domain import ModelRoute, Persona, TeamPolicy
from orchestrator.eligibility import is_route_eligible


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+#.:-]{1,63}")


@dataclass(frozen=True)
class RouteCandidate:
    model: str
    family: str
    score: float
    probability: float
    prior_score: float
    budget_bias: float
    terminal_success: float
    format_success: float
    contextual_success: float
    contextual_observations: int
    exploration: float
    calls: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "family": self.family,
            "score": self.score,
            "probability": self.probability,
            "prior_score": self.prior_score,
            "budget_bias": self.budget_bias,
            "terminal_success": self.terminal_success,
            "format_success": self.format_success,
            "contextual_success": self.contextual_success,
            "contextual_observations": self.contextual_observations,
            "exploration": self.exploration,
            "calls": self.calls,
        }


class ContextualRewardHead:
    """Small learned reward model for task-conditioned worker selection.

    Fugu's published selection head consumes a hidden state from a trained
    backbone. Those weights are not public, so the local router uses a stable
    hashing encoder and one regularized logistic head per persona/model route.
    The head is trained only from attributable live terminal outcomes.
    """

    def __init__(
        self,
        *,
        observations: list[dict[str, Any]],
        personas: set[str],
        models: set[str],
        dimensions: int = 512,
        epochs: int = 12,
        learning_rate: float = 0.12,
        l2: float = 0.0005,
    ):
        if dimensions < 32:
            raise ValueError("contextual head dimensions must be at least 32")
        self.dimensions = dimensions
        self._weights: dict[tuple[str, str], list[float]] = {}
        self._counts: Counter[tuple[str, str]] = Counter()
        normalized = [
            self._validate_observation(
                row,
                personas=personas,
                models=models,
            )
            for row in observations
        ]
        normalized.sort(
            key=lambda row: (
                row["persona"],
                row["model"],
                row["task"],
                row["reward"],
                row.get("run_id", ""),
                row.get("round", 0),
            )
        )
        for row in normalized:
            self._counts[(row["persona"], row["model"])] += 1
        self._fit(
            normalized,
            epochs=epochs,
            learning_rate=learning_rate,
            l2=l2,
        )

    def predict(self, *, task: str, persona: str, model: str) -> tuple[float, int]:
        key = (persona, model)
        count = self._counts[key]
        if not count:
            return 0.5, 0
        raw = self._sigmoid(
            self._dot(self._weights[key], self._features(task, persona))
        )
        confidence = count / (count + 8.0)
        return 0.5 + confidence * (raw - 0.5), count

    @property
    def observation_count(self) -> int:
        return sum(self._counts.values())

    @staticmethod
    def _validate_observation(
        row: dict[str, Any],
        *,
        personas: set[str],
        models: set[str],
    ) -> dict[str, Any]:
        task = str(row.get("task") or "").strip()
        persona = str(row.get("persona") or "").strip()
        model = str(row.get("model") or "").strip()
        reward = row.get("reward")
        if not task:
            raise ValueError("routing observation task must be non-empty")
        if persona not in personas:
            raise ValueError(f"routing observation has unknown persona: {persona!r}")
        if model not in models:
            raise ValueError(f"routing observation has unknown model: {model!r}")
        if (
            isinstance(reward, bool)
            or not isinstance(reward, (int, float))
            or not 0.0 <= float(reward) <= 1.0
        ):
            raise ValueError(
                f"routing observation {persona}/{model} reward must be within 0..1"
            )
        return {
            **row,
            "task": task,
            "persona": persona,
            "model": model,
            "reward": float(reward),
        }

    def _fit(
        self,
        observations: list[dict[str, Any]],
        *,
        epochs: int,
        learning_rate: float,
        l2: float,
    ) -> None:
        if not observations:
            return
        updates: Counter[tuple[str, str]] = Counter()
        for _ in range(epochs):
            for row in observations:
                key = (row["persona"], row["model"])
                weights = self._weights.setdefault(
                    key, [0.0] * self.dimensions
                )
                features = self._features(row["task"], row["persona"])
                prediction = self._sigmoid(self._dot(weights, features))
                error = row["reward"] - prediction
                step = learning_rate / math.sqrt(1.0 + updates[key] / 8.0)
                for index, value in features:
                    weights[index] += step * (
                        error * value - l2 * weights[index]
                    )
                updates[key] += 1

    def _features(self, task: str, persona: str) -> tuple[tuple[int, float], ...]:
        tokens = TOKEN_RE.findall(task.lower())[:256]
        names = [f"persona:{persona}", "bias"]
        names.extend(f"token:{token}" for token in tokens)
        names.extend(
            f"bigram:{left}:{right}"
            for left, right in zip(tokens, tokens[1:], strict=False)
        )
        values: Counter[int] = Counter()
        for name in names:
            digest = hashlib.blake2b(name.encode("utf-8"), digest_size=8).digest()
            encoded = int.from_bytes(digest, "big")
            index = encoded % self.dimensions
            sign = 1.0 if encoded & 1 else -1.0
            values[index] += sign
        magnitude = math.sqrt(sum(value * value for value in values.values())) or 1.0
        return tuple(
            (index, value / magnitude)
            for index, value in sorted(values.items())
        )

    @staticmethod
    def _dot(
        weights: list[float], features: tuple[tuple[int, float], ...]
    ) -> float:
        return sum(weights[index] * value for index, value in features)

    @staticmethod
    def _sigmoid(value: float) -> float:
        if value >= 0:
            inverse = math.exp(-value)
            return 1.0 / (1.0 + inverse)
        exponential = math.exp(value)
        return exponential / (1.0 + exponential)


class FuguRouter:
    """Local implementation of Fugu's performance-conditioned routing boundary.

    The proprietary Fugu backbone and selection-head weights are not public.
    This implementation combines calibrated role priors, aggregate reliability,
    and a learned task-conditioned reward head, then exposes a soft distribution
    over the configured worker pool. The Conductor remains responsible for
    multi-worker topology decisions.
    """

    def __init__(
        self,
        *,
        models: dict[str, ModelRoute],
        personas: dict[str, Persona],
        policy: TeamPolicy,
        outcomes: list[dict[str, Any]] = (),
        observations: list[dict[str, Any]] = (),
        temperature: float = 0.15,
    ):
        if temperature <= 0:
            raise ValueError("router temperature must be positive")
        self.models = models
        self.personas = personas
        self.policy = policy
        self.temperature = temperature
        active_personas = set(personas)
        active_models = set(models)
        self._outcomes: dict[tuple[str, str], dict[str, Any]] = {}
        for row in outcomes:
            if self._is_retired_history_row(
                row,
                personas=active_personas,
                models=active_models,
            ):
                continue
            normalized = self._validate_outcome(row)
            key = (normalized["persona"], normalized["model"])
            if key in self._outcomes:
                raise ValueError(f"duplicate routing outcome for {key[0]}/{key[1]}")
            self._outcomes[key] = normalized
        self._contextual_head = ContextualRewardHead(
            observations=[
                row
                for row in observations
                if not self._is_retired_history_row(
                    row,
                    personas=active_personas,
                    models=active_models,
                )
            ],
            personas=active_personas,
            models=active_models,
        )

    def rank(
        self,
        *,
        task: str,
        persona_id: str,
        model_ids: tuple[str, ...],
    ) -> tuple[RouteCandidate, ...]:
        if persona_id not in self.personas:
            raise ValueError(f"unknown persona: {persona_id}")
        if not model_ids:
            raise ValueError("router model pool must be non-empty")
        if len(set(model_ids)) != len(model_ids):
            raise ValueError("router model pool must not contain duplicate routes")
        unknown = [model_id for model_id in model_ids if model_id not in self.models]
        if unknown:
            raise ValueError(f"router model pool contains unknown routes: {unknown}")

        persona = self.personas[persona_id]
        eligible_model_ids = tuple(
            model_id
            for model_id in model_ids
            if is_route_eligible(
                task=task,
                persona_id=persona_id,
                model_id=model_id,
                policy=self.policy,
            )
        )
        if not eligible_model_ids:
            raise ValueError(
                f"router model pool has no eligible routes for {persona_id!r}"
            )
        task_traits = self._task_traits(task)
        total_calls = sum(
            int(self._outcome(persona_id, model_id).get("calls") or 0)
            for model_id in eligible_model_ids
        )
        scored: list[dict[str, Any]] = []
        for model_id in eligible_model_ids:
            model = self.models[model_id]
            outcome = self._outcome(persona_id, model_id)
            calls = int(outcome.get("calls") or 0)
            completed = int(outcome.get("format_successes") or 0)
            terminal_calls = int(outcome.get("terminal_calls") or 0)
            accepted_calls = int(outcome.get("accepted_calls") or 0)

            prior_score = self._prior_score(persona, model, task_traits)
            budget_bias = self.policy.family_budget_bias.get(model.family, 0.0)
            terminal_success = (accepted_calls + 1.0) / (terminal_calls + 2.0)
            format_success = (completed + 1.0) / (calls + 2.0)
            contextual_success, contextual_observations = (
                self._contextual_head.predict(
                    task=task,
                    persona=persona_id,
                    model=model_id,
                )
            )
            exploration = min(
                1.0,
                math.sqrt(math.log(total_calls + 2.0) / (calls + 1.0)),
            )
            score = (
                0.45 * prior_score
                + 0.20 * terminal_success
                + 0.10 * format_success
                + 0.20 * contextual_success
                + 0.05 * exploration
            )
            scored.append(
                {
                    "model": model,
                    "score": score,
                    "prior_score": prior_score,
                    "budget_bias": budget_bias,
                    "terminal_success": terminal_success,
                    "format_success": format_success,
                    "contextual_success": contextual_success,
                    "contextual_observations": contextual_observations,
                    "exploration": exploration,
                    "calls": calls,
                }
            )

        maximum = max(row["score"] for row in scored)
        weights = [
            math.exp((row["score"] - maximum) / self.temperature) for row in scored
        ]
        denominator = sum(weights)
        candidates = [
            RouteCandidate(
                model=row["model"].id,
                family=row["model"].family,
                score=round(float(row["score"]), 6),
                probability=round(weight / denominator, 6),
                prior_score=round(float(row["prior_score"]), 6),
                budget_bias=round(float(row["budget_bias"]), 6),
                terminal_success=round(float(row["terminal_success"]), 6),
                format_success=round(float(row["format_success"]), 6),
                contextual_success=round(float(row["contextual_success"]), 6),
                contextual_observations=int(row["contextual_observations"]),
                exploration=round(float(row["exploration"]), 6),
                calls=int(row["calls"]),
            )
            for row, weight in zip(scored, weights, strict=True)
        ]
        return tuple(
            sorted(
                candidates,
                key=lambda candidate: (-candidate.probability, candidate.model),
            )
        )

    def snapshot(
        self,
        *,
        task: str,
        persona_ids: tuple[str, ...],
        model_ids: tuple[str, ...],
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            persona_id: [
                candidate.as_dict()
                for candidate in self.rank(
                    task=task,
                    persona_id=persona_id,
                    model_ids=model_ids,
                )
            ]
            for persona_id in persona_ids
        }

    def _outcome(self, persona_id: str, model_id: str) -> dict[str, Any]:
        return self._outcomes.get(
            (persona_id, model_id),
            {
                "calls": 0,
                "format_successes": 0,
                "terminal_calls": 0,
                "accepted_calls": 0,
            },
        )

    @staticmethod
    def _validate_outcome(row: dict[str, Any]) -> dict[str, Any]:
        persona = str(row.get("persona") or "").strip()
        model = str(row.get("model") or "").strip()
        if not persona or not model:
            raise ValueError("routing outcomes require non-empty persona and model ids")

        counts: dict[str, int] = {}
        for field in (
            "calls",
            "format_successes",
            "terminal_calls",
            "accepted_calls",
        ):
            value = row.get(field, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"routing outcome {persona}/{model} has invalid {field}")
            counts[field] = value
        if counts["format_successes"] > counts["calls"]:
            raise ValueError("routing format successes cannot exceed calls")
        if counts["terminal_calls"] > counts["calls"]:
            raise ValueError("routing terminal calls cannot exceed calls")
        if counts["accepted_calls"] > counts["terminal_calls"]:
            raise ValueError("routing accepted calls cannot exceed terminal calls")
        return {"persona": persona, "model": model, **counts}

    @staticmethod
    def _is_retired_history_row(
        row: dict[str, Any],
        *,
        personas: set[str],
        models: set[str],
    ) -> bool:
        persona = str(row.get("persona") or "").strip()
        model = str(row.get("model") or "").strip()
        return bool(persona and model) and (
            persona not in personas or model not in models
        )

    def _task_traits(self, task: str) -> dict[str, float]:
        lower = task.lower()
        totals: Counter[str] = Counter()
        for keyword, boosts in self.policy.task_signals.items():
            if keyword.lower() in lower:
                totals.update(boosts)
        return {name: min(value, 1.0) for name, value in totals.items()}

    def _prior_score(
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
                strength in model.strengths for strength in persona.required_strengths
            ) / len(persona.required_strengths)
        task_fit = 0.0
        if task_traits:
            task_fit = sum(
                weight * self._effective_trait(model, trait)
                for trait, weight in task_traits.items()
            ) / sum(task_traits.values())
        preference = 0.0
        if model.id in persona.preferred_models:
            rank = persona.preferred_models.index(model.id)
            preference = (len(persona.preferred_models) - rank) / len(
                persona.preferred_models
            )
        return (
            0.7 * trait_fit
            + 0.2 * required_fit
            + 0.1 * task_fit
            + self.policy.preference_weight * preference
            + self.policy.family_budget_bias.get(model.family, 0.0)
        )

    @staticmethod
    def _effective_trait(model: ModelRoute, trait: str) -> float:
        raw = model.traits.get(trait, 0.5)
        return 0.5 + model.profile_confidence * (raw - 0.5)
