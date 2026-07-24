---
name: orchestrate
description: Run substantial research, security engineering, implementation, debugging, or verification work as a Fugu-routed Claude native dynamic workflow with independent personas and bounded retries.
disable-model-invocation: true
allowed-tools:
  - Workflow
  - Workflow(orchestrator:fugu-forum)
  - mcp__plugin_orchestrator_fugu__route_team
  - mcp__plugin_orchestrator_fugu__prepare_bead
  - mcp__plugin_orchestrator_fugu__checkpoint_bead
  - Agent(orchestrator:opus-worker, orchestrator:fable-neutral, orchestrator:codex-worker)
---

# Orchestrator

Run the user's task in Claude Code's native workflow runtime. The task is:

`$ARGUMENTS`

If the task is empty, ask for it. Otherwise:

1. Derive explicit acceptance criteria from the request and repository. Do not
   weaken criteria merely to get an accepting judgment.
2. Call `mcp__plugin_orchestrator_fugu__prepare_bead` with the absolute
   workspace, exact task, acceptance criteria, and an explicit Bead ID when the
   user supplied one. In a Beads workspace this atomically claims that issue or
   creates a dedicated task. If Beads exists and preparation fails, stop rather
   than running without durable project tracking. If `launch_allowed` is false,
   do not create a duplicate run; direct the user to resume the existing native
   workflow or explicitly reopen the Bead.
3. Call `mcp__plugin_orchestrator_fugu__route_team` with the exact task and
   workflow `security-research-forum`. Do not hand-select models before seeing
   the route plan.
4. Extract the returned `workflow_run_id` and `assignments`. Preserve each
   assignment's persona, model, `agent_type`, fallbacks, and reasons.
   Set `quick` to `true` only when the user requests a quick workflow or the
   task needs independent evidence and judgment but not competing hypotheses,
   adversarial cross-examination, or broad coverage. Quick mode still runs a
   real researcher, implementation worker, verifier, and judge.
   If the task contains the exact word `ultracheck`, preserve it in `task` and
   set `ultracheck` to `true`; the workflow will require a clean-process rerun,
   broad project checks, at least five refutation hypotheses, and a claim-level
   evidence ledger.
5. For security work, include the user's actual authorization and target
   boundary. If no authorization is present, restrict execution to analysis of
   local artifacts and defensive engineering.
6. Invoke the native `orchestrator:fugu-forum` workflow with structured args:

```json
{
  "task": "<exact user task>",
  "workspace": "<current absolute working directory>",
  "authorization": "<authorization and target boundary>",
  "acceptanceCriteria": ["<criterion>", "<criterion>"],
  "assignments": "<assignments returned by route_team>",
  "workflowRunId": "<workflow_run_id returned by route_team>",
  "tracking": "<prepare_bead result when enabled, otherwise null>",
  "quick": false,
  "ultracheck": false,
  "maxRounds": 6,
  "noProgressLimit": 2
}
```

Use `maxRounds: 2` when `quick` is true. Use `maxRounds: 6` for the full forum.

7. Tell the user the run is visible in `/workflows`. This is the only execution
   plane; never launch an external scheduler.
8. When the native workflow returns and Beads is enabled, call
   `mcp__plugin_orchestrator_fugu__checkpoint_bead` with its decision, summary,
   exact task, `workflowRunId`, `stopReason`, and queue. This write is
   serialized and also records idempotent per-route outcomes for Fugu. Close the
   Bead only when the workflow's deterministic gate returned `accept`.
9. Report the judgment, stop reason, queue totals, routed models, and real
   verification results. A blocked, rejected, no-progress, round-limited, or
   inconclusive result is not success.

Use a normal single-agent turn instead when the task is narrow enough that
independent evidence gathering and verification would add no value.

The native runtime owns scheduling. Fugu chooses routes but never launches work.
Worker return is testimony, not acceptance. Never have a subagent spawn another
orchestrator, and never run unbounded retry loops.
