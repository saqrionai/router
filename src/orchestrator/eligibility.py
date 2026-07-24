from __future__ import annotations

from orchestrator.domain import TeamPolicy


def is_security_task(task: str, policy: TeamPolicy) -> bool:
    normalized = task.casefold()
    return any(
        keyword.casefold() in normalized
        for keyword in policy.security_task_keywords
    )


def is_route_eligible(
    *,
    task: str,
    persona_id: str,
    model_id: str,
    policy: TeamPolicy,
) -> bool:
    if not is_security_task(task, policy):
        return True
    allowed_personas = policy.security_neutral_routes.get(model_id)
    return allowed_personas is None or persona_id in allowed_personas
