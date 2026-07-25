from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelRoute:
    id: str
    backend: str
    model: str
    context_window: int
    fallback_only: bool = False
    strengths: tuple[str, ...] = ()
    family: str = "unknown"
    styles: tuple[str, ...] = ()
    traits: dict[str, float] = field(default_factory=dict)
    profile_source: str = "uncalibrated"
    profile_confidence: float = 0.0
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class Persona:
    id: str
    title: str
    mission: str
    system_prompt: str
    preferred_models: tuple[str, ...]
    required_outputs: tuple[str, ...] = ()
    trait_weights: dict[str, float] = field(default_factory=dict)
    required_strengths: tuple[str, ...] = ()


@dataclass(frozen=True)
class TeamPolicy:
    role_fit_weight: float
    preference_weight: float
    family_budget_bias: dict[str, float]
    unique_model_bonus: float
    unique_family_bonus: float
    duplicate_model_penalty: float
    duplicate_family_penalty: float
    independence_model_penalty: float
    independence_family_penalty: float
    independence_pairs: tuple[tuple[str, str], ...]
    task_signals: dict[str, dict[str, float]] = field(default_factory=dict)
    security_task_keywords: tuple[str, ...] = ()
    security_neutral_routes: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class TeamAssignment:
    persona: str
    model: str
    score: float
    reasons: tuple[str, ...]
    fallback_order: tuple[str, ...]


@dataclass(frozen=True)
class TeamPlan:
    assignments: tuple[TeamAssignment, ...]
    total_score: float
    unique_models: int
    unique_families: int
    task_traits: dict[str, float]

    def assignment_for(self, persona_id: str) -> TeamAssignment:
        for assignment in self.assignments:
            if assignment.persona == persona_id:
                return assignment
        raise KeyError(persona_id)


@dataclass(frozen=True)
class Stage:
    id: str
    personas: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    parallel: bool = False
    kind: str = "agents"


@dataclass(frozen=True)
class Workflow:
    id: str
    title: str
    description: str
    requires_authorization: bool
    max_rounds: int
    stages: tuple[Stage, ...]


@dataclass(frozen=True)
class Scope:
    authorization: dict[str, Any]
    targets: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    execution: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Scope":
        return cls(
            authorization=dict(value.get("authorization") or {}),
            targets=tuple(str(item) for item in value.get("targets") or ()),
            allowed_actions=tuple(
                str(item) for item in value.get("allowed_actions") or ()
            ),
            execution=dict(value.get("execution") or {}),
        )

    def validate(self, *, authorization_required: bool) -> None:
        if not self.targets:
            raise ValueError("scope must declare at least one target")
        if authorization_required:
            summary = str(self.authorization.get("summary") or "").strip()
            owner = str(self.authorization.get("owner") or "").strip()
            if not summary or not owner:
                raise ValueError(
                    "authorized workflows require authorization.owner and "
                    "authorization.summary"
                )


@dataclass(frozen=True)
class CheckSpec:
    name: str
    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: int


@dataclass(frozen=True)
class AgentResult:
    persona: str
    model: str
    backend: str
    raw: str
    parsed: dict[str, Any] | None
    status: str
    usage: "Usage" = field(default_factory=lambda: Usage())


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    estimated_cost_usd: float | None = None

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


@dataclass(frozen=True)
class BoardMessage:
    thread: str
    author: str
    recipients: tuple[str, ...]
    kind: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_id: int | None = None


@dataclass(frozen=True)
class Artifact:
    local_id: str
    thread: str
    author: str
    title: str
    kind: str
    media_type: str
    content: str
    source_message_ids: tuple[int, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckResult:
    name: str
    argv: tuple[str, ...]
    cwd: Path
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
