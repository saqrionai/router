from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.domain import ModelRoute, Persona, Scope, Stage, TeamPolicy, Workflow


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _default_root() -> Path:
    configured = os.environ.get("ORCHESTRATOR_ROOT")
    candidates = (
        Path(configured).expanduser() if configured else None,
        Path.cwd(),
        Path.home() / "Documents" / "orchestrator",
        PROJECT_ROOT,
    )
    for candidate in candidates:
        if candidate is not None and (candidate / "config" / "models.json").is_file():
            return candidate
    return PROJECT_ROOT


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"configuration file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


@dataclass(frozen=True)
class AppConfig:
    root: Path
    models: dict[str, ModelRoute]
    personas: dict[str, Persona]
    workflows: dict[str, Workflow]
    team_policy: TeamPolicy

    @classmethod
    def load(cls, root: Path | None = None) -> "AppConfig":
        root = (root or _default_root()).resolve()
        config_dir = root / "config"

        models_raw = _read_json(config_dir / "models.json")
        models = {
            item["id"]: ModelRoute(
                id=item["id"],
                backend=item["backend"],
                model=item.get("model", item["id"]),
                context_window=int(item["context_window"]),
                strengths=tuple(item.get("strengths") or ()),
                family=str(item.get("family") or "unknown"),
                styles=tuple(item.get("styles") or ()),
                traits={
                    str(name): float(value)
                    for name, value in (item.get("traits") or {}).items()
                },
                profile_source=str(item.get("profile_source") or "uncalibrated"),
                profile_confidence=float(item.get("profile_confidence") or 0.0),
                reasoning_effort=item.get("reasoning_effort"),
            )
            for item in models_raw["models"]
        }

        personas_raw = _read_json(config_dir / "personas.json")
        personas = {
            item["id"]: Persona(
                id=item["id"],
                title=item["title"],
                mission=item["mission"],
                system_prompt=item["system_prompt"],
                preferred_models=tuple(item["preferred_models"]),
                required_outputs=tuple(item.get("required_outputs") or ()),
                trait_weights={
                    str(name): float(value)
                    for name, value in (item.get("trait_weights") or {}).items()
                },
                required_strengths=tuple(item.get("required_strengths") or ()),
            )
            for item in personas_raw["personas"]
        }

        policy_raw = _read_json(config_dir / "team-policy.json")
        team_policy = TeamPolicy(
            role_fit_weight=float(policy_raw.get("role_fit_weight", 1.0)),
            preference_weight=float(policy_raw.get("preference_weight", 0.05)),
            family_budget_bias={
                str(family): float(value)
                for family, value in (
                    policy_raw.get("family_budget_bias") or {}
                ).items()
            },
            unique_model_bonus=float(policy_raw.get("unique_model_bonus", 0.1)),
            unique_family_bonus=float(policy_raw.get("unique_family_bonus", 0.05)),
            duplicate_model_penalty=float(
                policy_raw.get("duplicate_model_penalty", 0.3)
            ),
            duplicate_family_penalty=float(
                policy_raw.get("duplicate_family_penalty", 0.08)
            ),
            independence_model_penalty=float(
                policy_raw.get("independence_model_penalty", 0.6)
            ),
            independence_family_penalty=float(
                policy_raw.get("independence_family_penalty", 0.15)
            ),
            independence_pairs=tuple(
                (str(pair[0]), str(pair[1]))
                for pair in policy_raw.get("independence_pairs") or ()
            ),
            task_signals={
                str(keyword): {
                    str(trait): float(value) for trait, value in boosts.items()
                }
                for keyword, boosts in (policy_raw.get("task_signals") or {}).items()
            },
            security_task_keywords=tuple(
                str(keyword)
                for keyword in policy_raw.get("security_task_keywords") or ()
            ),
            security_neutral_routes={
                str(model_id): tuple(str(persona) for persona in persona_ids)
                for model_id, persona_ids in (
                    policy_raw.get("security_neutral_routes") or {}
                ).items()
            },
        )

        workflows: dict[str, Workflow] = {}
        for path in sorted((config_dir / "workflows").glob("*.json")):
            item = _read_json(path)
            workflow = Workflow(
                id=item["id"],
                title=item["title"],
                description=item["description"],
                requires_authorization=bool(item.get("requires_authorization")),
                max_rounds=int(item.get("max_rounds", 1)),
                stages=tuple(
                    Stage(
                        id=stage["id"],
                        personas=tuple(stage.get("personas") or ()),
                        depends_on=tuple(stage.get("depends_on") or ()),
                        parallel=bool(stage.get("parallel")),
                        kind=stage.get("kind", "agents"),
                    )
                    for stage in item["stages"]
                ),
            )
            workflows[workflow.id] = workflow

        config = cls(
            root=root,
            models=models,
            personas=personas,
            workflows=workflows,
            team_policy=team_policy,
        )
        config.validate()
        return config

    def validate(self) -> None:
        for persona in self.personas.values():
            missing = [model for model in persona.preferred_models if model not in self.models]
            if missing:
                raise ValueError(
                    f"persona {persona.id!r} references unknown models: {missing}"
                )
            if not persona.trait_weights:
                raise ValueError(f"persona {persona.id!r} has no trait weights")
        for model in self.models.values():
            invalid_traits = {
                name: value
                for name, value in model.traits.items()
                if value < 0.0 or value > 1.0
            }
            if invalid_traits:
                raise ValueError(
                    f"model {model.id!r} has traits outside 0..1: {invalid_traits}"
                )
            if model.profile_confidence < 0.0 or model.profile_confidence > 1.0:
                raise ValueError(
                    f"model {model.id!r} profile_confidence must be within 0..1"
                )
        for workflow in self.workflows.values():
            stage_ids = {stage.id for stage in workflow.stages}
            for stage in workflow.stages:
                missing_personas = [
                    persona for persona in stage.personas if persona not in self.personas
                ]
                missing_dependencies = [
                    dependency
                    for dependency in stage.depends_on
                    if dependency not in stage_ids
                ]
                if missing_personas:
                    raise ValueError(
                        f"stage {stage.id!r} references unknown personas: "
                        f"{missing_personas}"
                    )
                if missing_dependencies:
                    raise ValueError(
                        f"stage {stage.id!r} references unknown dependencies: "
                        f"{missing_dependencies}"
                    )

    def workflow(self, workflow_id: str) -> Workflow:
        try:
            return self.workflows[workflow_id]
        except KeyError as exc:
            raise ValueError(f"unknown workflow: {workflow_id}") from exc

    def load_scope(self, path: Path) -> Scope:
        return Scope.from_dict(_read_json(path.resolve()))
