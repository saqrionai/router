# Architecture

## One Execution Plane

Claude Code native dynamic workflows are the sole scheduler. They own phases,
parallel agents, tool execution, worktrees, interruption, resumption, token
telemetry, and the `/workflows` interface.

Orchestrator adds four support boundaries:

| Component | Responsibility |
| --- | --- |
| Fugu MCP | Rank persona/model routes and return bounded fallbacks |
| Native workflow | Queue, evidence flow, verification, judgment, and revision |
| Agent telemetry | Normalize native hook events and supervise process-backed adapters |
| Beads bridge | Durable intake, dependencies, acceptance criteria, and checkpoint |

The Python routing package cannot start, resume, stop, or simulate workflow
workers. There is no alternate API, dashboard scheduler, or model gateway. A
plugin-local process supervisor observes one already-assigned external adapter
call; it does not choose work, create queue units, retry models, or schedule
agents.

## Native Queue

The full forum uses:

1. parallel researcher and hypothesis opening posts;
2. parallel exploit analysis and adversarial cross-examination;
3. one artifact worker;
4. independent artifact verification and evidence-coverage review;
5. an exact criterion-level judge; and
6. bounded revision waves when the judge returns actionable blockers.

Quick mode retains evidence, artifact, verification, and judgment while omitting
the competing hypothesis and cross-examination phases. UltraCheck adds broad
checks, a clean-process rerun, refutation hypotheses, hostile-input categories,
and a claim-level evidence ledger.

Each queue unit records persona, logical route, native agent type, attempted
fallbacks, per-attempt quality outcomes and reasons, status, round, and summary.
Worker return is testimony. Only the deterministic judge gate can accept the
task.

## Model Adapters

Opus 5, Fable 5, and the recovery-only Opus 4.8 route run as native Claude
agents. A GPT-5.6 assignment runs a native `codex-worker` adapter. That adapter
starts `codex-subagent` exactly once through the generic process supervisor,
polls that same process for output and descendant activity, returns the real
structured result, and cannot recursively orchestrate. A poll is observation,
not a retry.

Native Claude agents cannot be wrapped in that external launcher without losing
Claude Code's native workflow ownership. Lifecycle and tool hooks instead write
the same normalized heartbeat records for native sessions and subagents.
Claude's journal and `/workflows` remain authoritative during reasoning periods
that emit no hook event. Native control is still available: `/workflows` can
stop or restart a selected agent and pause or resume the run. The workflow
JavaScript API does not currently expose a per-agent cancellation handle to an
automatic watchdog while `await agent()` is in flight.

Logical model ids remain separate from transport:

```text
persona -> Fugu route -> native agent type -> provider worker -> evidence
```

Adding a provider means adding a logical route and one bounded adapter. It does
not create another scheduler.

## Evidence Gate

The judge receives the original criteria and evidence from independent units.
Acceptance requires:

- exactly one judgment row for every original criterion, in order;
- `passed` status for each row;
- non-empty direct artifact or reproducible machine evidence;
- supported completion claims; and
- no unresolved blockers.

JavaScript downgrades an unsupported `accept` to `revise`. Revision stops on
acceptance, rejection, no actionable next step, repeated no-progress, or the
round limit. Native agents additionally have hard turn caps and explicit
tool-call budgets.

## Beads Boundary

Beads is the canonical project queue and history. It is not the subagent chat
bus.

Before launch, the skill atomically claims a named Bead or creates a dedicated
one. An already-running Bead blocks duplicate workflow launch. After terminal
judgment, the skill performs one serialized checkpoint containing the task,
workflow id, stop reason, queue, models, and verdict. Only acceptance closes the
issue.

The workflow's in-memory queue remains native run state. Claude Code persists it
for interruption and resumption.

## Routing Learning

The route catalog contains behavioral priors with explicit confidence. Fugu
combines those priors with attributable native unit outcomes recorded at the
Beads checkpoint. Incomplete, cancelled, or unattributed work does not become a
positive label.

Historical pre-native run tables remain readable for local cost and artifact
inspection. They cannot execute work and are not a second control plane.

## Security Boundary

The workflow carries the user's authorization and target boundary to every
worker. Without authorization, execution is restricted to local read-only
analysis and defensive engineering. Fable is excluded from security tasks
because native fallback to Opus would make model attribution unreliable.
Authorization-required workflows enforce that exclusion even when the short
task text contains no configured security keyword.
Provider safeguards and usage policies still apply independently of routing.
