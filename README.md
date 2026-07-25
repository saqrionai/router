# Orchestrator

Orchestrator is a Fugu-routed, multi-model plugin for Claude Code native dynamic
workflows. Claude Code owns scheduling, parallelism, worktree isolation,
resumption, and the `/workflows` interface. Orchestrator contributes:

- six evidence-oriented personas;
- learned model/persona routing;
- bounded OpenAI delegation through the real Codex CLI;
- an explicit in-run work queue;
- independent criterion-level verification and judgment;
- no-progress and round-budget stops;
- structural UltraCheck gates;
- serialized Beads intake and result checkpoints; and
- native lifecycle telemetry.

There is one execution plane:

```text
Bead task and acceptance criteria
             |
             v
Claude native workflow scheduler
             |
             +--> Fugu routing MCP (policy only)
             |
             +--> Opus 5 native workers
             +--> Fable 5 neutral reviewers
             +--> codex-worker --> real GPT-5.6 call
             |
             v
criterion-level judge gate
             |
       accept / revise / reject / no-progress / round-limit
             |
             v
serialized Beads checkpoint
```

Fugu never starts a process. It ranks enabled routes using persona fit, task
traits, provider independence, capacity policy, and prior outcomes. A provider
adapter performs one bounded worker call and returns to the native workflow; it
cannot recursively schedule agents.

## Start A Run

The plugin is installed globally on this machine as
`orchestrator@skills-dir`. New Claude Code sessions load it automatically.
Existing first-party sessions can run `/reload-plugins`; sessions still showing
an old LiteLLM mapping must be exited and resumed through `~/bin/claude` so they
start with a clean first-party environment.

Start Claude Code in the target repository with the native Opus model:

```sh
claude
```

The installed `~/bin/claude` wrapper defaults to native Opus and removes stale
gateway overrides. A Codex transcript cannot be resumed as a Claude
conversation; Beads and repository artifacts provide the cross-client handoff.

Then run:

```text
/orchestrator:orchestrate continue
```

Use `/workflows` to inspect phases, queue activity, agents, prompts, tools,
tokens, and results. Claude Code saves workflow progress for session resumption.

In a repository with `.beads`, the skill first resumes the highest-priority
in-progress item. If none exists, it claims the highest-priority
dependency-ready item. Priority ties use most recent update and then issue ID.
A process-held lease prevents live clients from selecting the same Bead. An
explicit ID is only an override. An empty queue stops cleanly rather than
creating a placeholder. The skill appends one serialized checkpoint after the
native workflow returns and closes the issue only after deterministic
acceptance.

## Completion Contract

A worker returning is not completion. The judge must produce one row for every
exact acceptance criterion, with passing direct artifact or machine evidence.
JavaScript overrides an unsupported `accept` to `revise`.

Revision waves continue until one of these terminal conditions:

- all criteria pass with evidence;
- the judge rejects the result;
- two consecutive waves add no criterion-level evidence;
- the configured round budget is exhausted; or
- no actionable next step remains.

Use the exact word `ultracheck` to additionally require broad project checks, a
clean-process rerun, five refutation hypotheses, hostile-input coverage, and a
claim-level evidence ledger.

## Active Routes

The active catalog intentionally contains only:

- Opus 5 full-context and bounded routes;
- Fable 5 full-context and bounded neutral-review routes; and
- GPT-5.6 research, high, and Sol routes through Codex.

The Anthropic subscription carries high-volume work. GPT routes are used where
engineering strength or provider independence justifies the smaller OpenAI
allowance. Future providers such as K3 use another bounded adapter; the native
scheduler and Fugu policy remain unchanged.

Inspect policy without launching models:

```sh
orch models
orch personas
orch team --workflow security-research-forum --task "implement and verify"
orch route engineer --task "implement and debug the parser"
orch doctor
```

The remaining `orch show`, `runs`, `usage`, `bundle`, `artifacts`, and `eval`
commands are read-only access to archived runs. `orch` has no command that can
launch, resume, stop, probe, serve, or simulate model workers. There is no local
dashboard runtime; `/workflows` is the live interface.

## Files

- `claude-plugin/workflows/fugu-forum.js`: native queue and evidence gates.
- `claude-plugin/skills/orchestrate/SKILL.md`: native intake and Beads contract.
- `claude-plugin/agents/`: Opus, Fable, and Codex worker boundaries.
- `claude-plugin/examples/README.md`: native workflow examples.
- `src/orchestrator/mcp_server.py`: Fugu and Beads support tools.
- `config/models.json`: sole active route catalog.
- `config/personas.json`: persona contracts and route preferences.
- `config/team-policy.json`: composition and capacity policy.

See [Operations](docs/OPERATIONS.md), [Architecture](docs/ARCHITECTURE.md),
[Personas](docs/PERSONAS.md), and [Model Profiles](docs/MODEL_PROFILES.md).
