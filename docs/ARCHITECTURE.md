# Architecture

## Product Boundary

Orchestrator is a single-operator internal engineering harness. Claude Code is
allowed to own its native agents and Codex may be delegated bounded engineering
units because this plane handles Saqrion's own development work.

It is not Saqrion's sovereign customer inference plane. Customer workloads that
promise regional or sovereign residency require a separate data plane that
routes only to approved in-region GPU nodes and model containers, with
tenant-isolated credentials and state, enforceable residency policy, quotas,
usage attribution, provider/node health, and contractual failover behavior.
This repository's queue, evidence, judgment, telemetry, and learning contracts
may inform that product, but its Claude/Codex transports cannot serve it.

## One Native Execution Plane

Claude Code is the sole execution plane. Saved dynamic workflows own forum
phases plus sweep planning and final audit. Direct native Agent calls own sweep
writer isolation, reviewer fan-out, and serial integration. Claude Code owns
interruption, resumption, token telemetry, agent/task views, and `/workflows`.
There is no external scheduler.

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

The quick forum is the economy-first default. Standard forum is an explicit
escalation and uses:

1. parallel researcher and hypothesis opening posts;
2. one artifact worker;
3. independent artifact verification and evidence-coverage review;
4. an exact criterion-level judge; and
5. at most one revision when the judge returns actionable blockers.

Quick mode uses one artifact owner and one independent criterion checker with
one targeted revision only after an actionable evidence-backed failure.
Explicit full mode adds parallel exploit analysis and
adversarial cross-examination and permits at most two revisions. UltraCheck
uses the full graph and adds broad checks, a clean-process rerun, refutation
hypotheses, hostile-input categories, and a claim-level evidence ledger.

Each queue unit records persona, logical route, native agent type, attempted
fallbacks, per-attempt quality outcomes and reasons, status, round, and summary.
Worker return is testimony. Only the deterministic judge gate can accept the
task.

The sweep topology is for broad projects:

1. a routed planner inspects the real repository and emits at most 8 units by
   default, 24 for an explicit large sweep, or 64 only when explicitly asked;
2. JavaScript rejects cycles, unsafe paths, dirty writer bases, missing checks,
   and unordered overlapping write scopes;
3. the skill creates a native task DAG and launches dependency-ready owners in
   weighted parallel waves;
4. writing owners use direct native `Agent(..., isolation: worktree)` calls and
   return scoped commits;
5. high-risk units always receive independent persona review, critical units
   receive a second review in high-assurance mode, and lower-risk cohorts use
   deterministic sampling;
6. one serial integration agent inspects and cherry-picks accepted commits; and
7. one project judge resolves the original acceptance criteria against the
   resulting main checkout.

If that final gate blocks, it emits a deterministic revision packet containing
only failed criteria, high/critical findings, failed checks, integration
blockers, judge blockers, and next actions. The coordinator may run one
4-unit remediation sweep from the current accepted HEAD, then rerun the final
gate once. No changed Git/evidence state is `no-progress`; a second rejection
is `final-audit-failed-after-remediation`. Neither condition can recurse.

Queue capacity and active concurrency are separate. The default queue holds
8 units while weighted active capacity is 4. Fugu selects a persona/model
route for each unit role; it does not decide dependency readiness. When GPT is
the routed engineering primary, the first and every fourth writing unit use it
while Opus 5 carries the remaining writer fan-out. This keeps an independent
provider sample without spending the smaller OpenAI allowance on every unit.

This split is required by observed Claude Code 2.1.220 behavior. A real
repository probe showed that direct Agent calls honor `isolation: worktree`,
while agents spawned inside a dynamic workflow ignore custom-agent isolation
and explicit `cwd`. Writer agents therefore fail closed unless their current
Git directory is a linked worktree distinct from the main checkout.
Claude Code must use `worktree.baseRef: "head"`; its default `"fresh"` creates
subagent worktrees from `origin/HEAD` and would omit unpushed sweep commits.
`orch doctor` reports the configured base policy, and every writer still
verifies its exact dispatched base SHA before model launch.
Claude places active linked worktrees under `.claude/worktrees/`; integration
cleanliness excludes exactly that runtime path and no other dirty state.

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
automatic watchdog while `await agent()` is in flight. A live Claude Code
2.1.220 probe confirmed that `continue: false` from a workflow subagent's
`PreToolUse` hook stops only that agent, not a parallel peer. The runtime
reports that stopped call as a fulfilled empty result, however, so Orchestrator
keeps native runtime control authoritative and treats any empty structured
result as invalid rather than as successful work.

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
one. An already-running Bead blocks duplicate workflow launch. Forum and sweep
use the same lease and checkpoint boundary. After terminal
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
