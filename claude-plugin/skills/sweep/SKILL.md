---
name: sweep
description: Run a large software-engineering or authorized security project as a Fugu-routed native dependency sweep with parallel worktree owners, risk-based persona verification, serial integration, and Beads checkpoints.
disable-model-invocation: true
allowed-tools:
  - Workflow
  - Workflow(orchestrator:fugu-sweep)
  - Workflow(orchestrator:fugu-sweep-final)
  - mcp__plugin_orchestrator_fugu__route_team
  - mcp__plugin_orchestrator_fugu__prepare_bead
  - mcp__plugin_orchestrator_fugu__checkpoint_bead
  - Agent(orchestrator:opus-worker, orchestrator:opus-48-recovery, orchestrator:fable-neutral, orchestrator:codex-worker, orchestrator:sweep-planner, orchestrator:sweep-opus-worker, orchestrator:sweep-codex-worker, orchestrator:sweep-integrator)
  - TaskCreate
  - TaskUpdate
  - TaskList
  - TaskGet
  - TaskOutput
  - TaskStop
  - SendMessage
---

# Orchestrator Sweep

Run the user's project through Claude Code's native workflow and Agent
runtimes:

`$ARGUMENTS`

Use this skill for a substantial project with multiple independently ownable
files, components, experiments, or backlog units. Use
`/orchestrator:orchestrate` for one artifact that benefits from a bounded forum.
Use a normal turn for a narrow edit.

1. Call `mcp__plugin_orchestrator_fugu__prepare_bead` with the absolute
   workspace, exact instruction, supplied acceptance criteria, and an explicit
   Bead only when the user supplied one. Automatic intake resumes the
   highest-priority in-progress Bead, otherwise claims the highest-priority
   dependency-ready Bead. Stop when `launch_allowed` is false.
2. Hydrate the exact task and acceptance criteria from `resolved_task` and
   `resolved_acceptance_criteria`. Do not invent a replacement project.
   Normalize acceptance into an ordered JSON array of non-empty criterion
   strings before either workflow call. Never pass multiple criteria as one
   semicolon-delimited string.
3. Select `security-research-forum` for security, reverse engineering,
   firmware, vulnerability, exploit, fuzzing, crash, memory-safety, or binary
   work. Use `general-forum` only for clearly non-security work.
4. Call `mcp__plugin_orchestrator_fugu__route_team` with the hydrated task and
   selected routing profile. Preserve the returned persona assignments, model
   routes, agent types, reasons, and fallback orders.
5. For security work, include the user's actual authorization and target
   boundary. Without authorization, restrict execution to local artifact
   analysis and defensive engineering.
6. Launch the saved native `orchestrator:fugu-sweep` workflow to inspect the
   repository and produce a deterministically validated read-only plan:

```json
{
  "task": "<resolved_task>",
  "workspace": "<absolute current workspace>",
  "authorization": "<authorization and target boundary>",
  "acceptanceCriteria": ["<criterion 1>", "<criterion 2>"],
  "assignments": "<Fugu assignments>",
  "workflowRunId": "<Fugu workflow_run_id>",
  "tracking": "<prepare_bead result or null>",
  "securityTask": false,
  "highAssurance": false,
  "maxUnits": 8,
  "maxConcurrency": 4,
  "integrationChecks": []
}
```

Set `securityTask` accurately. The economy-first default is eight validated
units with four weighted active slots. Use 24 units and six slots only when the
user explicitly requests a large sweep. Use 64 units and eight slots only when
the user explicitly requests a 64-unit or 64-subagent sweep. Set
`highAssurance` only for an explicit `high assurance`, `full audit`, or
`ultracheck` request. Queue capacity and active concurrency are separate.

7. Stop if the planner returns anything except `status: planned`. Do not repair
   an invalid plan informally. Planning uses one low-effort, six-turn native
   agent and parses its JSON once without structured-output retries. Empty or
   malformed output is a typed `invalid-plan` infrastructure failure, never a
   reason to relaunch the planner in the same run. Tell the user which Bead was
   selected, the planned unit count, dependency shape, concurrency bound,
   persona routes, and risk-review counts.
8. Materialize every plan unit with `TaskCreate`, preserve `dependsOn` through
   task dependencies, and keep its unit ID in the task subject. Tasks are the
   live native queue; Beads remains the durable project history.
9. Run dependency-ready owner units in waves. Keep at most the selected weighted
   slot limit, which is 4 by default and never exceeds 8: light costs 1, medium
   costs 2, and heavy costs 4. The plan may be larger only by explicit request;
   never launch every queued build simultaneously. For each writing unit, make
   a **direct top-level native `Agent` call** with `isolation: worktree`:

   Before launching the first writer, require the effective Claude Code setting
   `worktree.baseRef` to be `"head"`. Claude's default `"fresh"` branches
   isolated subagents from `origin/HEAD`, which omits unpushed integrated or
   remediation commits. If the setting is not `"head"`, checkpoint an
   infrastructure failure and stop before any writer launch. The per-worker
   exact base-SHA preflight remains mandatory even when the setting is correct.

   - GPT-5.6 owner route: `orchestrator:sweep-codex-worker`;
   - Opus 5 owner route: `orchestrator:sweep-opus-worker`;
   - Fable is never a writing owner and never handles operational security;
   - Opus 4.8 is recovery-only after a primary route is unavailable, malformed,
     or deterministically degraded.

   Respect each unit's planner-assigned `ownerModel`. When Fugu selects GPT for
   engineering, the planner assigns GPT to the first and then every fourth
   writing unit; Opus 5 carries the others. This preserves cross-provider
   sampling without exhausting the smaller OpenAI allowance during large
   sweeps.

   Beads is centralized coordinator state. Writing and read-only unit workers
   must not invoke `bd` or access `.beads` from a worktree; only the parent in
   the main checkout claims and checkpoints the selected Bead.

   Do not launch a writing owner through `Workflow.agent()`: Claude Code
   2.1.220 ignores custom-agent worktree isolation and explicit `cwd` there.
   Direct native `Agent(..., isolation: worktree)` is the supported path and
   has been verified against a real repository. Dispatch the main workspace,
   base SHA, unit ID, objective, exact acceptance criteria, declared paths,
   dependencies, checks, authorization, route, and this required result
   contract:

```json
{
  "status": "completed|blocked|failed",
  "unitId": "unit-id",
  "summary": "observed result",
  "branch": "worktree branch",
  "worktree": "absolute isolated path",
  "baseSha": "sha",
  "commitSha": "sha or empty",
  "changedPaths": [],
  "claims": [],
  "evidence": [],
  "checks": [],
  "unresolved": [],
  "nextActions": []
}
```

   A writing result is usable only when its worktree differs from the main
   workspace, Git reports a linked worktree, and its initial HEAD exactly
   equals the dispatched planned base. A base mismatch means Claude retained a
   stale session checkout: stop the worker before model launch, checkpoint an
   infrastructure failure, and restart Claude from the current main HEAD.
   Never merge or rebase around session-base drift. Its real commit must
   descend from the planned base, every changed path must be declared, and all
   required checks must pass.
   A returned response alone is never success. A read-only unit may use the
   Fugu-selected standard agent without worktree isolation and must return
   concrete evidence. Mark the corresponding native task completed only after
   its deterministic gate passes.
   Record the exact opaque agent/task identifier returned by every launch and
   use only that identifier for output retrieval, messages, cancellation, or
   restart. Never synthesize a task ID from a label, teammate name, unit ID, or
   session ID. If a returned text view is truncated, verify the declared commit
   and checks directly from Git rather than asking a completed writer to rerun.
   Poll active IDs with `TaskGet` or `TaskOutput`. Status changes, tool events,
   token/output growth, supervisor descendant activity, and new Git evidence
   are heartbeats. Ten minutes with none of those signals is `no-progress`:
   stop that exact ID with `TaskStop`, record the evidence, and try at most one
   declared fallback. Never stop an agent merely because it has not called a
   tool while its token/output counter is growing. A failed, duplicate,
   malformed, or no-progress unit blocks only its dependency descendants;
   continue every unrelated dependency-ready unit.
10. Launch the plan's `reviewCount` independent read-only reviewers after an
    owner returns. Reviewers inspect the actual commit and worktree evidence,
    attempt to falsify the unit criteria, and return findings with severity and
    evidence. They must not edit. Critical units receive one review by default
    and two under high assurance; high-risk units receive one, security-medium
    units receive one, and lower-risk cohorts use the planner's deterministic
    sample. A critical/high finding or unsupported criterion blocks integration.
11. After all accepted owners and required reviewers finish, launch exactly one
    direct `orchestrator:sweep-integrator` Agent in the main workspace. Supply
    commits in dependency order, declared paths, planned base SHA, and real
    integration checks. It serially inspects and cherry-picks only accepted
    commits. Claude-owned `.claude/worktrees/**` entries from currently active
    direct agents are expected runtime state and are excluded from the
    cleanliness query; every other dirty or untracked path blocks. Stop on
    unexpected paths, a missing commit, conflict, or failed check. Do not guess
    through semantic conflicts.
12. Launch the saved read-only `orchestrator:fugu-sweep-final` workflow with the
    original task, the same ordered acceptance-criteria array, authorization,
    assignments,
    workflow run ID, security flag, validated plan, complete owner results,
    review results, integration result, `highAssurance`, and `revisionRound: 0`.
    The default runs one independent artifact audit and a separate exact
    criterion-level judge. High assurance adds a parallel coverage audit.
    Accept only when that workflow returns `status: accepted`.
13. If the first final workflow returns `status: blocked`,
    `stopReason: final-audit-failed`, and `remediationAllowed: true`, run
    exactly one bounded remediation cycle:

    - Require its `revisionPacket` to contain at least one failed criterion,
      high/critical finding, failed check, integration blocker, judge blocker,
      or next action. The packet is the remediation scope; do not add unrelated
      improvements.
    - Checkpoint the Bead immediately with decision `revise`, the first final
      result, and the current queue. This preserves the rejected judgment
      before more work starts.
    - Launch `orchestrator:fugu-sweep` once with the original task and
      acceptance criteria, current main checkout, same authorization and
      assignments, the same `highAssurance`, `remediationRound: 1`, the exact `revisionPacket`,
      `maxUnits: 4`, and the original integration checks. A malformed or
      blocked remediation plan is terminal for this run. Pass
      `revisionPacket` inline as the JSON object returned by the final
      workflow; a file path, attachment, artifact reference, or
      `revisionPacketPath` field is invalid.
    - The first remediation `Workflow` call consumes the single planning
      attempt, including when input validation returns `status: rejected`
      before an agent launches. Never correct arguments or retry that call in
      the same run. Checkpoint the typed rejection and leave the Bead in
      progress.
    - Materialize and execute only the remediation units through steps 8-11.
      Preserve every accepted commit already on main. Owners must start from
      the current post-integration HEAD; never replay or replace the initial
      plan.
    - Compare the resulting Git HEAD, accepted commit set, passed checks, and
      criterion evidence with the state before remediation. If none changed,
      stop with typed `no-progress`; do not spend the final rerun.
    - Launch `orchestrator:fugu-sweep-final` one final time with
      the same `highAssurance`, `revisionRound: 1`, and the cumulative initial
      plus remediation evidence.
      If it blocks, its typed stop is
      `final-audit-failed-after-remediation`. Never plan a second remediation
      cycle.

    A first final result with `remediationAllowed: false`, an empty revision
    packet, no progress, or a second rejection leaves the Bead in progress and
    stops honestly. A worker merely returning does not count as remediation.
14. Checkpoint the Bead with
   `mcp__plugin_orchestrator_fugu__checkpoint_bead`. Pass the exact decision,
   summary, task, workflow run ID, stop reason, and queue. Close only an
   independently accepted sweep. If startup fails, checkpoint
   `inconclusive` with `infrastructure-failure`.
15. Report the planned unit count, wave count, model/persona routes, accepted and
   blocked units, resulting Git HEAD, final checks, and judgment.

Every paid wave must advance at least one exact acceptance criterion through a
real commit, check, device measurement, artifact, primary-evidence finding, or
typed actionable blocker. If a wave only repeats prior analysis, stop as
`no-progress` before launching reviewers, remediation, or another wave.

The skill is the native coordinator. Fugu routes persona/model pairs but never
starts agents. The planner and final audit appear under `/workflows`; owner,
reviewer, and integration fan-out appears in Claude Code's native agent and task
views. This split is one Orchestrator stack, not a separate daemon or chat bus.
It uses the same direct worktree Agent primitive as Claude Code's built-in
`/batch`, while retaining Fugu routes, persona review, exact evidence gates, and
Beads checkpoints.

Do not invoke `/batch` from this skill. Claude Code marks `/batch` as
user-invocable only, so a model or workflow cannot call it reliably. Do not use
`EnterWorktree` inside an agent, create an external scheduler, nest another
orchestration layer, silently integrate an unverified change, push, or open PRs
without explicit user direction.
