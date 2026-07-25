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
before Claude starts and defaults to native Opus. Do not launch
`~/.local/bin/claude` directly.

Claude and Codex maintain different conversation stores. Starting Claude in a
repository that was previously used only by Codex creates a new Claude
conversation; it cannot convert or resume the Codex transcript. The repository,
Beads history, and committed artifacts are the durable handoff. Use `claude`
for that first native session. Use `claude -c` only after the repository has a
useful Claude session to continue.

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
/orchestrator:orchestrate continue
```

For a broad project with multiple independent implementation units, use:

```text
/orchestrator:sweep continue
```

The planner workflow validates a dependency DAG. The skill queues at most 64
native tasks, keeps a bounded weighted worker pool active, launches writing
owners through direct native worktree Agents, applies independent persona
review by risk, and serially cherry-picks accepted commits. A final saved
workflow independently audits the integrated checkout. It never pushes or
opens PRs without explicit operator direction.

`/batch` remains an interactive user command and cannot be invoked by a skill
or workflow. Sweep uses the same supported direct Agent worktree primitive with
Fugu routing, risk review, exact acceptance gates, and Beads checkpoints.
Planning and final audit are visible under `/workflows`; owner and reviewer
fan-out is visible in Claude Code's native agent/task views.
The coordinator retains Claude's opaque ID for each launched agent. Labels and
teammate names are display metadata and must never be reconstructed into task
IDs for result retrieval or cancellation.
Native status, tool, token/output, supervisor-process, and Git changes count as
heartbeats. Ten minutes without any signal stops that exact agent and permits
one declared fallback. Its dependency descendants remain blocked, while
unrelated ready units continue.

The skill performs this sequence:

1. automatically resume the highest-priority in-progress Bead, otherwise claim
   the highest-priority dependency-ready Bead;
2. hydrate the task and acceptance criteria from that Bead;
3. ask the Fugu MCP for persona/model assignments;
4. launch `orchestrator:fugu-forum`;
5. run queued research, implementation, verification, and judgment units;
6. revise while evidence progresses and budget remains; and
7. write one serialized result checkpoint to the Bead.

Fugu and Beads tools do not launch models.
The skill selects `security-research-forum` for security, reverse engineering,
firmware, crash, vulnerability, and other authorization-required work. Clearly
non-security tasks use `general-forum`, which keeps Fable available for neutral
verification.

Opus 4.8 is recovery-only and always comes after every eligible normal Opus 5
or GPT route. A GPT provider failure therefore falls back to Opus 5 before
4.8; 4.8 remains available only when the normal routes are unavailable,
malformed, or deterministically degraded.

## Workflow Control

Use `/workflows` for progress, agents, prompts, tool calls, token totals,
pausing, stopping, and resumption. Select an agent and press `x` to stop it or
`r` to restart it. Press `p` at run level to pause or resume the workflow.
Native progress is saved by Claude Code.
There is no local API worker, background dashboard scheduler, or LaunchAgent.

The standard workflow permits at most two rounds: the initial artifact and one
evidence-backed revision. Quick mode permits one round. Explicit `full forum`
and UltraCheck permit at most three rounds. Every mode stops after two
consecutive no-progress revisions. A worker returning successfully only changes
its queue unit to `returned`; it does not accept the task.

Each native agent also has a hard turn cap and a smaller substantive tool-call
budget. Recovery agents use at most three substantive tool calls, may retry a
no-signal machine check only once, and must keep a shell command's combined
declared worst-case runtime below 90 seconds. A second no-signal result ends
testing and returns a blocked or partial result instead of consuming another
verification loop. Standard mode is the default: two parallel opening units,
one artifact writer, two parallel verification units, and one judge, with at
most one revision. Ask for a `quick workflow` to use one opening unit, one
writer, one verifier, one judge, and no revision. Ask for `full forum` only for
ambiguous, adversarial, or broad work; it adds parallel cross-examination and
allows at most two revisions.

Process-backed model agents use
`claude-plugin/bin/agent-supervisor`. It launches one durable process, records
stdout/stderr growth, descendant process creation, and process-tree CPU time,
returns a heartbeat every poll window, stops after ten minutes without any of
those progress signals, and enforces a 30-minute total deadline. A poll observes
the existing agent; it never launches a retry. Native Claude `agent()` calls
remain under Claude Code's `/workflows` runtime because wrapping them in an
external process would discard native pause, stop, save, and resume behavior.

Native Claude sessions and subagents publish the same lifecycle concept through
Claude hooks. `SessionStart`, `SubagentStart`, `PreToolUse`, `PostToolUse`,
`SubagentStop`, and `SessionEnd` update normalized records under
`~/.local/state/orchestrator/heartbeats/<session>/<agent>.json`. These records
show the last native lifecycle or tool event. Claude's own journal and
`/workflows` remain authoritative for long reasoning calls that do not emit a
tool event. The native runtime supports manual per-agent stop and restart, but
workflow JavaScript does not expose an asynchronous cancellation handle that a
plugin watchdog can call while `await agent()` is in flight.

A disposable two-agent probe on Claude Code 2.1.220 established the narrower
hook behavior: a `PreToolUse` hook returning `continue: false` stopped only the
triggering workflow agent while its in-flight peer completed normally.
`PreToolUse` included the workflow `agent_id`. The stopped call was nevertheless
reported to workflow JavaScript as a fulfilled empty result instead of a typed
cancellation. Orchestrator therefore does not use hook cancellation as its
primary native control surface. Its structured-result gate rejects the empty
result and may fall back safely; operators should use `/workflows` or
`TaskStop` when they need an immediate, explicitly represented native stop.

## Beads Queue

Beads is project state, dependency ordering, and durable history. It is not the
subagent chat bus.

```sh
bd ready --json
bd show ISSUE --json
```

Normal continuation requires no issue lookup:

```text
/orchestrator:orchestrate continue
```

Automatic intake considers `in_progress` items before dependency-ready open
items. Within each group it sorts by priority, most recent update, and ID. It
holds a per-Bead process lease, so another live Claude client skips that item
and can claim the next eligible one. An explicit `bead=ISSUE` remains available
as an override. When no in-progress or ready work remains, `continue` stops
cleanly instead of creating a meaningless placeholder Bead.

Beads uses a single writer. Intake and final checkpoints are serialized, and
transient Dolt lock conflicts receive bounded retries. Native workflow state
handles interruption between those checkpoints. The Beads checkpoint is
written before route-learning observations, so a failed `bd` operation cannot
train the router on state that was never made durable. `accept` closes the
Bead; no-progress, rejection, or round exhaustion marks it blocked.

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

Provider failures use the Fugu assignment's declared fallback order. Every
eligible normal Opus 5 or GPT route is attempted before native Opus 4.8.
Recovery-only 4.8 activates only after normal routes are unavailable, invalid,
or fail deterministic evidence-quality checks; the queue records the attempted
model and exact reason. Model disagreement alone never triggers fallback.
Adding a future K3 adapter does not change queue or judge semantics.

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
