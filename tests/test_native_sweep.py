import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SWEEP = ROOT / "claude-plugin" / "workflows" / "fugu-sweep.js"
FINAL = ROOT / "claude-plugin" / "workflows" / "fugu-sweep-final.js"
SWEEP_SKILL = ROOT / "claude-plugin" / "skills" / "sweep" / "SKILL.md"
OPUS_WORKER = ROOT / "claude-plugin" / "agents" / "sweep-opus-worker.md"
CODEX_WORKER = ROOT / "claude-plugin" / "agents" / "sweep-codex-worker.md"
INTEGRATOR = ROOT / "claude-plugin" / "agents" / "sweep-integrator.md"
PLANNER = ROOT / "claude-plugin" / "agents" / "sweep-planner.md"


def run_node(source: str) -> None:
    subprocess.run(
        ["node", "--input-type=module", "-e", source],
        cwd=ROOT,
        text=True,
        check=True,
    )


def test_sweep_uses_read_only_workflows_and_direct_isolated_writers() -> None:
    planner = SWEEP.read_text(encoding="utf-8")
    final = FINAL.read_text(encoding="utf-8")
    skill = SWEEP_SKILL.read_text(encoding="utf-8")
    opus = OPUS_WORKER.read_text(encoding="utf-8")
    codex = CODEX_WORKER.read_text(encoding="utf-8")
    integrator = INTEGRATOR.read_text(encoding="utf-8")
    bounded_planner = PLANNER.read_text(encoding="utf-8")

    assert "Math.min(Number(input.maxUnits || 64), 64)" in planner
    assert "Math.min(Number(input.maxConcurrency || 8), 12)" in planner
    assert "const plannerModel = 'opus-5-bounded'" in planner
    assert "function ownerRoutes(unit, writingOrdinal)" in planner
    assert "writingOrdinal % 4 === 1" in planner
    assert "READ-ONLY SWEEP PLANNER" in planner
    assert "agentType: 'orchestrator:sweep-planner'" in planner
    assert "schema: planSchema" not in planner
    assert "parsePlannerOutput(rawPlan)" in planner
    assert "planner returned empty output" in planner
    assert "Do not emit persona-review" in planner
    assert "sweep-opus-worker" not in planner
    assert "sweep-codex-worker" not in planner
    assert "sweep-integrator" not in planner
    assert "semantically distinct units" in planner
    assert "Deduplicate units" in planner
    assert "every writes=false unit MUST return paths=[]" in planner
    assert "Every unit id MUST be lowercase" in planner
    assert "Every writing path MUST be relative to the" in planner
    assert "^[a-z0-9][a-z0-9._-]{0,63}$" in planner
    assert "await parallel([" in final
    assert "READ-ONLY FINAL SWEEP AUDIT" in final
    assert "criterionErrors" in final
    assert r".replace(/^\d+[.)]\s+/, '')" in final
    assert "CRITERION[${index}]=${JSON.stringify(item)}" in final
    assert "candidates.filter(model => !model.startsWith('fable-5'))" in final
    assert "'codex-sol-high'," in final
    assert "right === 'codex-sol-high'" in final
    assert "'openai'," in final
    assert "'anthropic'," in final
    assert "Workflow(orchestrator:fugu-sweep)" in skill
    assert "Workflow(orchestrator:fugu-sweep-final)" in skill
    assert "direct top-level native `Agent` call" in skill
    assert "`isolation: worktree`" in skill
    assert "ignores custom-agent worktree isolation and explicit `cwd`" in skill
    assert "at most 8 weighted slots" in skill
    assert "TaskCreate" in skill
    assert "TaskStop" in skill
    assert "Ten minutes with none of those signals is `no-progress`" in skill
    assert "blocks only its dependency descendants" in skill
    assert "ordered JSON array of non-empty criterion" in skill
    assert "Never pass multiple criteria as one" in skill
    assert "exact opaque agent/task identifier" in skill
    assert "Never synthesize a task ID" in skill
    assert "Do not invoke `/batch`" in skill
    assert "parses its JSON once without structured-output retries" in skill
    assert "effort: low" in bounded_planner
    assert "maxTurns: 6" in bounded_planner
    assert "tools: Read, Glob, Grep, Bash" in bounded_planner
    assert "This is a single attempt" in bounded_planner
    assert "isolation: worktree" in opus
    assert "isolation: worktree" in codex
    assert "do not call `EnterWorktree`" in opus
    assert "do not call `EnterWorktree`" in codex
    assert "tools: EnterWorktree" not in codex
    assert "codex-subagent" in codex
    assert "effort: low" in codex
    assert "maxTurns: 10" in codex
    assert "Do not draft, inspect, or append the prompt in phases" in codex
    for worker in (opus, codex):
        normalized_worker = " ".join(worker.split())
        assert "current HEAD does not equal the dispatched base SHA" in worker
        assert "typed infrastructure failure" in worker
        assert "Do not invoke `bd`" in worker
        assert "read or write `.beads`" in normalized_worker
    assert "Beads is centralized coordinator state" in skill
    assert "restart Claude from the current main HEAD" in skill
    assert "':(exclude).claude/worktrees/**'" in integrator
    assert "Do not ignore any other `.claude` path" in integrator


def test_planner_output_parser_is_single_attempt_and_deterministic() -> None:
    source = SWEEP.read_text(encoding="utf-8")
    start = source.index("function parsePlannerOutput")
    end = source.index("\n\nphase('Plan')", start)
    parser = source[start:end]
    cases = [
        [{"status": "completed"}, "completed", ""],
        ['{"status":"blocked"}', "blocked", ""],
        ["```json\n{\"status\":\"completed\"}\n```", "completed", ""],
        ["", None, "planner returned empty output"],
        ["not json", None, "planner output is not valid JSON"],
        ["[]", None, "planner output is not a JSON object"],
    ]
    script = (
        f"{parser}\n"
        f"const cases = {json.dumps(cases)};\n"
        "for (const [value, status, error] of cases) {\n"
        "  const parsed = parsePlannerOutput(value);\n"
        "  if ((parsed.plan?.status || null) !== status) process.exit(1);\n"
        "  if (!String(parsed.error).includes(error)) process.exit(1);\n"
        "}\n"
    )
    run_node(script)


def test_plan_validator_rejects_cycles_escapes_and_parallel_overlap() -> None:
    source = SWEEP.read_text(encoding="utf-8")
    start = source.index("function normalPath")
    end = source.index("function stableBucket")
    helpers = source[start:end]
    base_unit = {
        "title": "unit",
        "objective": "do work",
        "kind": "implementation",
        "writes": True,
        "risk": "medium",
        "resource": "light",
        "persona": "engineer",
        "paths": ["src/a/**"],
        "dependsOn": [],
        "acceptanceCriteria": ["real criterion"],
        "checks": ["true"],
    }
    cases = [
        {
            "name": "valid",
            "plan": {
                "status": "completed",
                "baseSha": "a" * 40,
                "repoClean": True,
                "units": [
                    {**base_unit, "id": "a"},
                    {**base_unit, "id": "b", "paths": ["src/b/**"]},
                ],
            },
            "pattern": None,
        },
        {
            "name": "valid-read-only",
            "plan": {
                "status": "completed",
                "baseSha": "a" * 40,
                "repoClean": True,
                "units": [
                    {
                        **base_unit,
                        "id": "research",
                        "kind": "research",
                        "writes": False,
                        "persona": "researcher",
                        "paths": [],
                        "checks": ["rg pattern src"],
                    },
                ],
            },
            "pattern": None,
        },
        {
            "name": "read-only-write-scope",
            "plan": {
                "status": "completed",
                "baseSha": "a" * 40,
                "repoClean": True,
                "units": [
                    {
                        **base_unit,
                        "id": "research",
                        "kind": "research",
                        "writes": False,
                        "persona": "researcher",
                        "paths": ["src/a/**"],
                        "checks": ["rg pattern src"],
                    },
                ],
            },
            "pattern": "read-only unit cannot claim write paths",
        },
        {
            "name": "cycle",
            "plan": {
                "status": "completed",
                "baseSha": "a" * 40,
                "repoClean": True,
                "units": [
                    {**base_unit, "id": "a", "dependsOn": ["b"]},
                    {
                        **base_unit,
                        "id": "b",
                        "paths": ["src/b/**"],
                        "dependsOn": ["a"],
                    },
                ],
            },
            "pattern": "cycle",
        },
        {
            "name": "escape",
            "plan": {
                "status": "completed",
                "baseSha": "a" * 40,
                "repoClean": True,
                "units": [
                    {**base_unit, "id": "a", "paths": ["../outside"]},
                ],
            },
            "pattern": "unsafe",
        },
        {
            "name": "overlap",
            "plan": {
                "status": "completed",
                "baseSha": "a" * 40,
                "repoClean": True,
                "units": [
                    {**base_unit, "id": "a"},
                    {**base_unit, "id": "b", "paths": ["src/a/file.c"]},
                ],
            },
            "pattern": "overlapping",
        },
    ]
    script = (
        "const maxUnits = 64;\n"
        "const personas = new Set(['researcher','challenger','exploiter',"
        "'engineer','verifier','judge']);\n"
        "const risks = new Set(['low','medium','high','critical']);\n"
        "const kinds = new Set(['research','implementation','test','artifact']);\n"
        "const resources = new Set(['light','medium','heavy']);\n"
        f"{helpers}\n"
        f"const cases = {json.dumps(cases)};\n"
        "for (const item of cases) {\n"
        "  const errors = validatePlan(item.plan);\n"
        "  if (item.pattern === null && errors.length) throw new Error(item.name);\n"
        "  if (item.pattern !== null && !errors.some(e => e.includes(item.pattern))) "
        "throw new Error(item.name + ':' + JSON.stringify(errors));\n"
        "}\n"
    )

    run_node(script)


def test_risk_policy_is_deterministic_and_escalates_high_risk() -> None:
    source = SWEEP.read_text(encoding="utf-8")
    start = source.index("function stableBucket")
    end = source.index("function agentTypeForModel")
    helpers = source[start:end]
    script = (
        "const workflowRunId = 'native-test';\n"
        "const securityTask = false;\n"
        f"{helpers}\n"
        "const critical = {id:'c',risk:'critical'};\n"
        "const high = {id:'h',risk:'high'};\n"
        "const medium = {id:'m',risk:'medium'};\n"
        "const low = {id:'l',risk:'low'};\n"
        "if (verificationCount(critical, false) !== 2) process.exit(1);\n"
        "if (verificationCount(high, false) !== 1) process.exit(1);\n"
        "if (verificationCount(medium, true) !== 1) process.exit(1);\n"
        "if (verificationCount(low, true) !== 1) process.exit(1);\n"
        "if (verificationCount(low, false) !== "
        "verificationCount(low, false)) process.exit(1);\n"
    )

    run_node(script)


def test_writing_owner_routes_remove_fable_and_keep_read_only_fable() -> None:
    source = SWEEP.read_text(encoding="utf-8")
    codex_start = source.index("function isCodexRoute")
    codex_end = source.index("function agentTypeForModel")
    owner_start = source.index("function ownerRoutes")
    owner_end = source.index("function parsePlannerOutput")
    helper = source[codex_start:codex_end] + source[owner_start:owner_end]
    script = (
        "function routes(persona) {\n"
        "  if (persona === 'verifier') return ['fable-5-bounded'];\n"
        "  return ['codex-sol-high', 'opus-5-bounded'];\n"
        "}\n"
        f"{helper}\n"
        "const writing = ownerRoutes({writes:true,persona:'verifier'}, 1);\n"
        "if (JSON.stringify(writing) !== JSON.stringify(['opus-5-bounded'])) "
        "process.exit(1);\n"
        "const reading = ownerRoutes({writes:false,persona:'verifier'}, 0);\n"
        "if (JSON.stringify(reading) !== JSON.stringify(['fable-5-bounded'])) "
        "process.exit(1);\n"
    )

    run_node(script)


def test_final_gate_requires_two_exact_audits_and_judge_acceptance() -> None:
    source = FINAL.read_text(encoding="utf-8")

    assert "sweep-artifact-verifier" in source
    assert "sweep-coverage-verifier" in source
    assert "audits.forEach" in source
    assert "integration did not complete" in source
    assert "judge did not accept" in source
    assert "unresolved critical or high finding" in source
    assert "status: gateErrors.length ? 'blocked' : 'accepted'" in source
    assert "Do not edit, commit, push" in source
