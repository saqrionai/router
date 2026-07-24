from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "claude-plugin" / "workflows" / "fugu-forum.js"
CODEX_AGENT = ROOT / "claude-plugin" / "agents" / "codex-worker.md"
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

    assert "maxTurns: 4" in source
    assert "exactly once" in source
    assert "--skip-git-repo-check" in source
    assert 'CODEX_SUBAGENT_MODEL="gpt-5.6-sol"' in source
    assert "CODEX_SUBAGENT_REASONING_EFFORT=" in source
    assert "CODEX_SUBAGENT_SANDBOX=" in source
    assert "Do not inspect the wrapper" in source
    assert "Do not call it a second time" in source.replace("\n", " ")


def test_orchestrate_skill_defaults_to_automatic_bead_intake() -> None:
    source = ORCHESTRATE_SKILL.read_text(encoding="utf-8")

    assert "With no ID, intake is" in source
    assert "highest-priority `in_progress`" in source
    assert "`resolved_task`" in source
    assert "another live client skips that Bead" in source


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
