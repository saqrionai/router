import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "claude-plugin" / "workflows" / "fugu-forum.js"
CODEX_AGENT = ROOT / "claude-plugin" / "agents" / "codex-worker.md"
OPUS_48_AGENT = ROOT / "claude-plugin" / "agents" / "opus-48-recovery.md"
ORCHESTRATE_SKILL = (
    ROOT / "claude-plugin" / "skills" / "orchestrate" / "SKILL.md"
)


def test_quick_workflow_has_bounded_graph_and_queue_evidence() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "const quick = Boolean(input.quick)" in source
    assert "quick ? 2 : 8" in source
    assert "const cross = quick" in source
    assert "NATIVE QUEUE SNAPSHOT:" in source
    assert "${excerpt(queueSnapshot(), 12000)}" in source


def test_codex_adapter_is_one_call_and_non_git_safe() -> None:
    source = CODEX_AGENT.read_text(encoding="utf-8")

    assert "maxTurns: 18" in source
    assert "exactly once" in source
    assert "--skip-git-repo-check" in source
    assert "agent-supervisor" in source
    assert "--window 240 --idle-limit 600" in source
    assert "observing the same process, not retrying the model" in source
    assert "--max-runtime 1800" in source
    assert 'CODEX_SUBAGENT_MODEL="gpt-5.6-sol"' in source
    assert "CODEX_SUBAGENT_REASONING_EFFORT=" in source
    assert "CODEX_SUBAGENT_SANDBOX=" in source
    assert "Do not inspect the wrapper" in source
    assert "Do not call it a second time" in source.replace("\n", " ")
    assert "status: failed" in source
    assert "Never normalize provider failure" in source


def test_orchestrate_skill_defaults_to_automatic_bead_intake() -> None:
    source = ORCHESTRATE_SKILL.read_text(encoding="utf-8")

    assert "With no ID, intake is" in source
    assert "highest-priority `in_progress`" in source
    assert "`resolved_task`" in source
    assert "another live client skips that Bead" in source


def test_opus_48_is_a_quality_gated_native_recovery_route() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    agent = OPUS_48_AGENT.read_text(encoding="utf-8")

    assert "workerDegradationReasons" in workflow
    assert "judgeDegradationReasons" in workflow
    assert "validUltraResult" in workflow
    assert "ultraDegradationReasons" in workflow
    assert "outcome: 'degraded'" in workflow
    assert "outcome: 'unavailable'" in workflow
    assert "providerFailureReason" in workflow
    assert "orchestrator:opus-48-recovery" in workflow
    skill = ORCHESTRATE_SKILL.read_text(encoding="utf-8")
    assert "Agent(orchestrator:opus-worker, orchestrator:opus-48-recovery" in skill
    assert "model: claude-opus-4-8" in agent
    assert "maxTurns: 8" in agent
    assert "at most three substantive tool calls" in agent


def test_native_agents_stop_repeating_no_signal_checks() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    recovery = OPUS_48_AGENT.read_text(encoding="utf-8")

    for source in (workflow, recovery):
        assert "zero-signal" in source
        assert "After a second no-signal result" in source.replace("\n", " ")
        assert "below 90 seconds" in source
    assert workflow.count("${executionBudget}") == 2


def test_global_workflow_limits_are_rethrown_instead_of_routed() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(
        r"function isAbortError\(error\) \{.*?\n\}",
        source,
        flags=re.DOTALL,
    )
    assert match is not None
    cases = [
        [{"name": "WorkflowAgentCapError"}, True],
        [{"name": "WorkflowBudgetExceededError"}, True],
        [{"message": "Workflow agent() call cap reached"}, True],
        [{"message": "Workflow token budget exceeded"}, True],
        [{"message": "budget exhausted"}, True],
        [{"message": "provider temporarily unavailable"}, False],
    ]
    script = (
        f"{match.group(0)}\n"
        f"const cases = {json.dumps(cases)};\n"
        "for (const [error, expected] of cases) {\n"
        "  if (isAbortError(error) !== expected) process.exit(1);\n"
        "}\n"
    )

    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        cwd=ROOT,
    )


def test_provider_failure_is_detected_for_workers_and_judges() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(
        r"function providerFailureReason\(result\) \{.*?\n\}",
        source,
        flags=re.DOTALL,
    )
    assert match is not None
    script = (
        f"{match.group(0)}\n"
        "if (!providerFailureReason({status: 'failed', summary: 'timeout'})) "
        "process.exit(1);\n"
        "if (providerFailureReason({status: 'blocked', summary: 'real blocker'})) "
        "process.exit(1);\n"
    )

    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        cwd=ROOT,
    )
    assert source.count("providerFailureReason(") >= 3
    assert "judge provider failure" in source


def test_retired_execution_planes_are_absent() -> None:
    retired = (
        "api.py",
        "backends.py",
        "probe.py",
        "routing.py",
        "runner.py",
        "supervisor.py",
        "workflow.py",
    )

    for name in retired:
        assert not (ROOT / "src" / "orchestrator" / name).exists()
    assert not (ROOT / "web" / "package.json").exists()
