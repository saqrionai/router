# Operations

## Install And Activate

On this machine the Claude plugin is installed for every project through a live
symlink:

```text
~/.claude/skills/orchestrator -> ~/Documents/orchestrator/claude-plugin
```

Confirm it with:

```sh
claude plugin details orchestrator@skills-dir
```

New Claude Code sessions load it automatically. In an existing first-party
session, run `/reload-plugins` to load a new plugin version without discarding
the conversation.

Plugin reload does not replace process environment. A session whose status line
still shows a LiteLLM model mapping must be exited and resumed through the
first-party wrapper:

```sh
~/bin/claude --resume <session-id> --model opus
```

That wrapper removes inherited gateway, Bedrock, Vertex, and Foundry overrides
before Claude starts. Do not launch `~/.local/bin/claude` directly.

Codex can share Fugu routing policy and Beads tools through the
`orchestrator-fugu` MCP server. It does not gain Claude's Workflow runtime and
must not create a second forum scheduler. Restart or resume Codex after adding
the MCP server because tool configuration is captured at session startup.

## Execution Plane

Claude Code native dynamic workflows are the only scheduler. Keep the main
session on native Opus:

```sh
cd ~/Documents/ios
claude --model opus
```

Start substantial work with:

```text
/orchestrator:orchestrate <objective and exact acceptance criteria>
```

The skill performs this sequence:

1. derive exact acceptance criteria;
2. claim or create a Bead when `.beads` is present;
3. ask the Fugu MCP for persona/model assignments;
4. launch `orchestrator:fugu-forum`;
5. run queued research, implementation, verification, and judgment units;
6. revise while evidence progresses and budget remains; and
7. write one serialized result checkpoint to the Bead.

Fugu and Beads tools do not launch models.

## Workflow Control

Use `/workflows` for progress, agents, prompts, tool calls, token totals,
pausing, stopping, and resumption. Native progress is saved by Claude Code.
There is no local API worker, background dashboard scheduler, or LaunchAgent.

The workflow defaults to six rounds, allows at most eight, and stops after two
consecutive no-progress revisions. A worker returning successfully only changes
its queue unit to `returned`; it does not accept the task.

Each native agent also has a hard turn cap and a smaller substantive tool-call
budget. For bounded tasks, ask for a `quick workflow`; it runs evidence,
artifact, verification, and judgment units while omitting the competing
hypothesis and cross-examination phases and defaults to two rounds. Use the full
forum for ambiguous, adversarial, or broad work.

## Beads Queue

Beads is project state, dependency ordering, and durable history. It is not the
subagent chat bus.

```sh
bd ready --json
bd show ISSUE --json
```

Reference a specific item:

```text
/orchestrator:orchestrate bead=ISSUE Complete this Bead using its existing
scope and acceptance criteria.
```

Beads uses a single writer. Intake and final checkpoints are serialized. Native
workflow state handles interruption between those checkpoints. `accept` closes
the Bead; no-progress, rejection, or round exhaustion marks it blocked.

## Model Routing

```sh
orch models
orch personas
orch team --workflow security-research-forum --task "implement and verify"
orch route verifier --task "falsify the proposed fix" --json
```

The workflow currently uses native Opus and Fable agents. GPT-5.6 assignments
enter a native `codex-worker`, which performs exactly one real
`codex-subagent` call and returns its structured result. This is external model
transport under native scheduling, not another orchestrator.

Provider failures use the Fugu assignment's declared fallback order. Adding a
future K3 adapter does not change queue or judge semantics.

## UltraCheck

Include `ultracheck` in the task:

```text
/orchestrator:orchestrate ultracheck this parser fix. Acceptance: the regression
test and applicable project checks pass from a clean process, and every
completion claim has reproducible evidence.
```

Acceptance then requires:

- acceptance, tests, build, typecheck, and lint categories;
- a clean-process rerun;
- at least five independent refutation hypotheses;
- empty, null, zero, negative, huge, malformed, Unicode, duplicate, error-path,
  and boundary input categories; and
- a non-empty claim-level evidence ledger.

Inapplicable categories must be present and justified. A confident judge cannot
bypass missing structural evidence.

## Diagnostics

```sh
orch doctor
claude auth status
claude plugin validate ~/Documents/orchestrator/claude-plugin
node --check ~/Documents/orchestrator/claude-plugin/workflows/fugu-forum.js
```

Lifecycle events are appended to:

```text
~/.local/state/orchestrator/claude-native-events.jsonl
```

Historical local runs remain readable:

```sh
orch runs
orch show RUN_ID
orch usage RUN_ID
orch artifacts RUN_ID
orch bundle RUN_ID
```

Those commands cannot execute or continue work.

## Long Runs

Dynamic workflows are designed for long-running, resumable work, but completion
still needs explicit gates and budgets. Infrastructure failure, authentication,
usage limits, or an operator stop can interrupt a run. Resume it through Claude
Code; do not start a duplicate scheduler.

Noninteractive `claude -p` waits at most 600 seconds for background work by
default. A smoke or CI invocation that intentionally waits for a longer native
workflow must set `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`. Interactive sessions
do not need that override; inspect, stop, or resume them with `/workflows`.
