import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "claude-plugin" / "workflows" / "fugu-forum.js"
FRONTIER_WORKFLOW = ROOT / "claude-plugin" / "workflows" / "fugu-frontier.js"
FRONTIER_FINAL = (
    ROOT / "claude-plugin" / "workflows" / "fugu-frontier-final.js"
)
FRONTIER_AGENT = ROOT / "claude-plugin" / "agents" / "frontier-planner.md"
CODEX_AGENT = ROOT / "claude-plugin" / "agents" / "codex-worker.md"
OPUS_48_AGENT = ROOT / "claude-plugin" / "agents" / "opus-48-recovery.md"
ORCHESTRATE_SKILL = (
    ROOT / "claude-plugin" / "skills" / "orchestrate" / "SKILL.md"
)
MCP_LAUNCHER = ROOT / "claude-plugin" / "bin" / "orchestrator-mcp"


def test_workflow_modes_have_bounded_graph_and_queue_evidence() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "const standardForum = !fullForum" in source
    assert "const quick = !fullForum && !standardForum" in source
    assert "const fullForum = ultracheck" in source
    assert "const mode = fullForum ? 'full' : standardForum ? 'standard' : 'quick'" in source
    assert "const defaultMaxRounds = fullForum ? 3 : 2" in source
    assert "const cross = fullForum" in source
    assert "const opening = quick" in source
    assert "const verification = quick" in source
    assert source.count("? []") >= 2
    assert "QUICK DELIVERY GATE:" in source
    assert "NATIVE QUEUE SNAPSHOT:" in source
    assert "${excerpt(queueSnapshot(), 12000)}" in source


def test_codex_adapter_is_one_call_and_non_git_safe() -> None:
    source = CODEX_AGENT.read_text(encoding="utf-8")

    assert "effort: low" in source
    assert "maxTurns: 10" in source
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
    assert "not draft, inspect, or append the prompt in phases" in source
    assert "Do not call it a second time" in source.replace("\n", " ")
    assert "status: failed" in source
    assert "Never normalize provider failure" in source


def test_orchestrate_skill_defaults_to_automatic_bead_intake() -> None:
    source = ORCHESTRATE_SKILL.read_text(encoding="utf-8")

    assert "Without an ID, intake remains" in source
    assert "highest-priority `in_progress`" in source
    assert "`resolved_task`" in source
    assert "another live" in source
    assert "client skips that Bead" in source
    assert "`quick`: the economy-first default" in source
    assert "`standard`: only when" in source
    assert "Full mode additionally runs parallel cross-examination" in source
    assert "inspect_frontier" in source
    assert "fugu-frontier" in source
    assert "The second selection is an independence candidate only" in source


def test_frontier_planner_is_bounded_read_only_and_single_attempt() -> None:
    workflow = FRONTIER_WORKFLOW.read_text(encoding="utf-8")
    agent = FRONTIER_AGENT.read_text(encoding="utf-8")

    assert "maxTurns: 6" in agent
    assert "effort: low" in agent
    assert "Do not edit files, claim or update Beads" in agent
    assert "Use at most three" in agent
    assert workflow.count("await agent(") == 1
    assert "Math.min(Number(input.maxSelected || 2), 2)" in workflow
    assert "overlapping write scopes" in workflow
    assert "dependencyHypotheses" in workflow


def test_frontier_validator_rejects_overlap_and_unknown_beads() -> None:
    source = FRONTIER_WORKFLOW.read_text(encoding="utf-8")
    start = source.index("function normalPath")
    end = source.index("\n\nphase('Inspect frontier')")
    helpers = source[start:end]
    valid = {
        "status": "completed",
        "summary": "advance independent deliverables",
        "selected": [
            {
                "issueId": "one",
                "reason": "highest value",
                "firstStep": "edit one",
                "expectedEvidence": "focused test",
                "risk": "medium",
                "capability": "owner",
                "writes": True,
                "paths": ["src/one/**"],
                "checks": ["pytest -q tests/test_one.py"],
            },
            {
                "issueId": "two",
                "reason": "independent unblock",
                "firstStep": "inspect two",
                "expectedEvidence": "trace",
                "risk": "low",
                "capability": "researcher",
                "writes": False,
                "paths": [],
                "checks": [],
            },
        ],
        "dependencyHypotheses": [],
    }
    overlap = json.loads(json.dumps(valid))
    overlap["selected"][1]["writes"] = True
    overlap["selected"][1]["paths"] = ["src/one/nested/**"]
    unknown = json.loads(json.dumps(valid))
    unknown["selected"][1]["issueId"] = "missing"
    script = (
        f"{helpers}\n"
        "const ids = new Set(['one', 'two']);\n"
        f"const valid = {json.dumps(valid)};\n"
        f"const overlap = {json.dumps(overlap)};\n"
        f"const unknown = {json.dumps(unknown)};\n"
        "if (validatePlan(valid, ids, 2).length) process.exit(1);\n"
        "if (!validatePlan(overlap, ids, 2).some(x => x.includes('overlapping'))) process.exit(2);\n"
        "if (!validatePlan(unknown, ids, 2).some(x => x.includes('unknown selected'))) process.exit(3);\n"
    )

    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        cwd=ROOT,
    )


def test_two_bead_delivery_uses_isolated_owners_and_parallel_checks() -> None:
    skill = ORCHESTRATE_SKILL.read_text(encoding="utf-8")
    final = FRONTIER_FINAL.read_text(encoding="utf-8")

    assert "prepare_frontier" in skill
    assert "atomically acquires separate process leases" in skill
    assert "Launch both owners together" in skill
    assert "`isolation: worktree`" in skill
    assert "sweep-integrator" in skill
    assert "Checkpoint the two Beads one at a time" in skill
    assert "Do not also launch the single-Bead forum" in skill
    assert "items.length > 2" in final
    assert "await parallel(calls)" in final
    assert final.count("await agent(") == 1
    assert "criterionErrors" in final
    assert "owner commit is not present in serial integration evidence" in final
    assert "writing owner returned no check evidence" in final
    assert "result.decision === 'accept'" in final


def test_frontier_final_gate_requires_exact_supported_criteria() -> None:
    source = FRONTIER_FINAL.read_text(encoding="utf-8")
    start = source.index("function criterionErrors")
    end = source.index("\n\nasync function checkItem", start)
    validator = source[start:end]
    expected = ["focused test passes", "artifact exists"]
    passing = [
        {
            "criterion": "focused test passes",
            "status": "passed",
            "evidence": ["pytest: 1 passed"],
        },
        {
            "criterion": "artifact exists",
            "status": "passed",
            "evidence": ["src/artifact.py:1"],
        },
    ]
    unsupported = json.loads(json.dumps(passing))
    unsupported[1]["evidence"] = []
    script = (
        f"{validator}\n"
        f"const expected = {json.dumps(expected)};\n"
        f"const passing = {json.dumps(passing)};\n"
        f"const unsupported = {json.dumps(unsupported)};\n"
        "if (criterionErrors(passing, expected).length) process.exit(1);\n"
        "if (!criterionErrors(unsupported, expected).some(x => x.includes('lacks direct evidence'))) process.exit(2);\n"
        "if (!criterionErrors([], []).some(x => x.includes('no acceptance criteria'))) process.exit(3);\n"
    )

    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        cwd=ROOT,
    )


def test_mcp_launcher_pins_current_beads_without_overriding_operator() -> None:
    source = MCP_LAUNCHER.read_text(encoding="utf-8")

    assert '[ -z "${ORCHESTRATOR_BD_BIN:-}" ]' in source
    assert "command -v brew" in source
    assert 'ORCHESTRATOR_BD_BIN="${brew_bd}"' in source
    assert "export ORCHESTRATOR_BD_BIN" in source


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
