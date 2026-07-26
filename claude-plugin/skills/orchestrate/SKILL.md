---
name: orchestrate
description: Run substantial research, security engineering, implementation, debugging, or verification work as a Fugu-routed Claude native dynamic workflow with independent personas and bounded retries.
disable-model-invocation: true
allowed-tools:
  - Workflow
  - Workflow(orchestrator:fugu-frontier)
  - Workflow(orchestrator:fugu-forum)
  - mcp__plugin_orchestrator_fugu__route_team
  - mcp__plugin_orchestrator_fugu__inspect_frontier
  - mcp__plugin_orchestrator_fugu__prepare_bead
  - mcp__plugin_orchestrator_fugu__checkpoint_bead
  - Agent(orchestrator:opus-worker, orchestrator:opus-48-recovery, orchestrator:fable-neutral, orchestrator:codex-worker, orchestrator:frontier-planner)
---

# Orchestrator

Run the user's task in Claude Code's native workflow runtime. The task is:

`$ARGUMENTS`

If the task is empty, ask for it. Otherwise:

1. Extract acceptance criteria explicitly supplied by the user. For a generic
   request such as `continue`, do not invent a new scope before reading Beads.
2. When the user did not supply a Bead ID, call
   `mcp__plugin_orchestrator_fugu__inspect_frontier` with the absolute
   workspace and `limit: 8`. This is read-only and does not claim work. If it
   returns multiple candidates, invoke the native `orchestrator:fugu-frontier`
   workflow with the exact user instruction, workspace, returned candidates,
   and `maxSelected: 2`. Use the first validated selection as the issue ID for
   this run. The second selection is an independence candidate only: do not
   claim or execute it until the parallel frontier executor owns isolated
   work. Do not persist planner dependency hypotheses; they require separate
   evidence admission. If the plan is blocked or invalid, stop and report its
   exact errors. With one candidate, use its ID directly. With no candidates,
   let preparation decide whether a specific new task should create a Bead or
   whether a generic continuation is complete.
3. Call `mcp__plugin_orchestrator_fugu__prepare_bead` with the absolute
   workspace, exact user instruction, initial acceptance criteria, and the
   supplied or frontier-selected issue ID. Without an ID, intake remains
   deterministic: resume the highest-priority `in_progress` item, otherwise
   claim the highest-priority dependency-ready item, breaking ties by most
   recent update and then ID. The MCP holds a process lease so another live
   client skips that Bead. It creates a dedicated Bead only when no resumable
   or ready candidate exists.
4. Read `resolved_task`, `resolved_acceptance_criteria`, `selection`, and the
   selected `snapshot` from preparation. Use the resolved values from this
   point forward; they hydrate a vague `continue` request with the Bead title,
   description, design, notes, and acceptance contract. Add criteria required
   by the repository only when they strengthen rather than replace the Bead's
   contract. If Beads exists and preparation fails, stop rather than running
   without durable tracking. If `launch_allowed` is false, do not create a
   duplicate run; report the active candidate IDs and direct the user to the
   existing native workflow.
5. Select the routing profile, then call
   `mcp__plugin_orchestrator_fugu__route_team` with `resolved_task` and that
   workflow. Use `security-research-forum` whenever the task or hydrated Bead
   involves security, vulnerability research, reverse engineering, firmware,
   exploitation, binary analysis, memory safety, fuzzing, CVEs, crash analysis,
   or any authorization-required target. Use `general-forum` only when the
   work is clearly non-security. Do not hand-select models before seeing the
   route plan.
6. Extract the returned `workflow_run_id` and `assignments`. Preserve each
   assignment's persona, model, `agent_type`, fallbacks, and reasons.
   Select one explicit execution mode:
   - `quick`: the economy-first default;
   - `standard`: only when the task contains `standard forum`; and
   - `full`: only when the task contains `full forum`.
   Quick mode runs one owner and one independent criterion checker, with no
   mandatory opening panel. If the checker returns an actionable,
   evidence-backed failure, it permits one targeted owner/checker revision.
   The owner gathers research only as needed to advance the artifact.
   Standard mode runs two parallel opening units, one artifact writer, two
   parallel verification units, and one judge, with at most one revision.
   Full mode additionally runs parallel cross-examination and allows at most
   two revisions. If both quick and full are requested, full wins.
   If the task contains the exact word `ultracheck`, preserve it in `task` and
   set `ultracheck` and `fullForum` to `true`; the workflow will require a
   clean-process rerun, broad project checks, at least five refutation
   hypotheses, and a claim-level evidence ledger.
7. For security work, include the user's actual authorization and target
   boundary. If no authorization is present, restrict execution to analysis of
   local artifacts and defensive engineering.
8. Invoke the native `orchestrator:fugu-forum` workflow with structured args:

```json
{
  "task": "<resolved_task from prepare_bead>",
  "workspace": "<current absolute working directory>",
  "authorization": "<authorization and target boundary>",
  "acceptanceCriteria": "<resolved_acceptance_criteria plus any strengthened repository criteria>",
  "assignments": "<assignments returned by route_team>",
  "workflowRunId": "<workflow_run_id returned by route_team>",
  "tracking": "<prepare_bead result when enabled, otherwise null>",
  "quick": true,
  "standardForum": false,
  "fullForum": false,
  "ultracheck": false,
  "maxRounds": 2,
  "noProgressLimit": 2
}
```

Use `maxRounds: 2` for quick or standard and `3` for full or UltraCheck. Quick
normally ends after its two-call first round; its second round runs only after
an actionable, evidence-backed checker failure. The workflow enforces these
ceilings even if a larger value is supplied.

9. Tell the user the selected Bead and whether it was resumed, claimed, or
   created. The run is visible in `/workflows`. This is the only execution
   plane; never launch an external scheduler.
10. When the native workflow returns and Beads is enabled, call
   `mcp__plugin_orchestrator_fugu__checkpoint_bead` with its decision, summary,
   exact task, `workflowRunId`, `stopReason`, and queue. This write is
   serialized and also records idempotent per-route outcomes for Fugu. Close the
   Bead only when the workflow's deterministic gate returned `accept`. If
   routing or workflow startup fails after preparation, checkpoint
   `inconclusive` with stop reason `infrastructure-failure` and an empty queue;
   this keeps the Bead in progress while releasing its live-client lease.
11. Report the judgment, stop reason, queue totals, routed models, and real
   verification results. A blocked, rejected, no-progress, round-limited, or
   inconclusive result is not success.

Use a normal single-agent turn instead when the task is narrow enough that
independent evidence gathering and verification would add no value.

Economy is a delivery constraint, not a quality waiver. Each paid workflow must
target at least one concrete Bead acceptance criterion and end with a changed
artifact, real check, commit, device measurement, new primary evidence, or a
typed blocker with the smallest actionable next step. Do not spend another
forum round to restate existing evidence.

Use `/orchestrator:sweep` instead when the user explicitly asks for batching,
fan-out, a large project, many independent changes, or high-throughput work
across multiple components. The sweep owns decomposition, worktree isolation,
dependency waves, and risk-based review; do not force that topology through the
single-artifact forum.

The native runtime owns scheduling. Fugu chooses routes but never launches work.
Worker return is testimony, not acceptance. Never have a subagent spawn another
orchestrator, and never run unbounded retry loops.
