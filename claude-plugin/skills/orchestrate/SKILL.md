---
name: orchestrate
description: Run substantial research, security engineering, implementation, debugging, or verification work as a Fugu-routed Claude native dynamic workflow with independent personas and bounded retries.
disable-model-invocation: true
allowed-tools:
  - Workflow
  - Workflow(orchestrator:fugu-frontier)
  - Workflow(orchestrator:fugu-frontier-final)
  - Workflow(orchestrator:fugu-forum)
  - mcp__plugin_orchestrator_fugu__route_team
  - mcp__plugin_orchestrator_fugu__inspect_frontier
  - mcp__plugin_orchestrator_fugu__prepare_bead
  - mcp__plugin_orchestrator_fugu__prepare_frontier
  - mcp__plugin_orchestrator_fugu__checkpoint_bead
  - mcp__plugin_orchestrator_fugu__admit_discoveries
  - Agent(orchestrator:opus-worker, orchestrator:opus-48-recovery, orchestrator:fable-neutral, orchestrator:codex-worker, orchestrator:frontier-planner, orchestrator:sweep-opus-worker, orchestrator:sweep-codex-worker, orchestrator:sweep-integrator)
  - TaskCreate
  - TaskUpdate
  - TaskGet
  - TaskOutput
  - TaskStop
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
   When the validated plan selects two Beads, use the delivery fan-out below
   and return after its checkpoints. Do not also launch the single-Bead forum.

### Two-Bead Delivery Fan-Out

1. Call `mcp__plugin_orchestrator_fugu__prepare_frontier` once with the two
   selected IDs, exact operator instruction, and supplied acceptance criteria.
   This atomically acquires separate process leases before either run starts.
   Stop if both leases are not granted; never fall back to untracked work.
2. Use each returned issue's distinct `resolved_task`,
   `resolved_acceptance_criteria`, and snapshot. Call `route_team` separately
   for each task and preserve separate workflow run IDs. Choose the owner route
   from the planner capability, using engineer for writing work and researcher
   for a read-only default. Fable cannot own writes or operational security.
3. Require a clean main checkout except `.claude/worktrees/**`, record its
   exact HEAD, and require effective `worktree.baseRef: "head"` before writing.
   If any preflight fails, checkpoint both issues as `inconclusive` with
   `infrastructure-failure`, releasing their leases.
4. Create one native task per Bead. Launch both owners together in one direct
   top-level Agent fan-out, never through `Workflow.agent()`:
   - writing Opus route: `orchestrator:sweep-opus-worker` with
     `isolation: worktree`;
   - writing GPT route: `orchestrator:sweep-codex-worker` with
     `isolation: worktree`; and
   - read-only route: its normal Fugu agent without isolation.

   Supply the Bead ID as the unit ID, main workspace, planned base SHA, exact
   task and criteria, planner-declared paths and checks, authorization, and
   routed model. One owner has exclusive responsibility for one Bead. Workers
   must not invoke `bd` or read `.beads`. A writing result is usable only when
   it comes from a linked worktree distinct from main, started at the exact
   base SHA, changed only declared paths, ran every declared check, and
   produced one real descendant commit. Require this result shape:

```json
{
  "status": "completed|blocked|failed",
  "unitId": "bead-id",
  "summary": "observed result",
  "branch": "worktree branch",
  "worktree": "absolute path",
  "baseSha": "planned sha",
  "commitSha": "real sha or empty",
  "changedPaths": [],
  "claims": [],
  "evidence": [],
  "checks": [],
  "unresolved": [],
  "nextActions": []
}
```

5. Poll only the exact opaque native IDs returned by launch. Output, token,
   tool, task-status, process-supervisor, and Git growth are heartbeats. After
   ten minutes with no signal, stop only that owner and continue the unrelated
   one. There is no automatic owner retry in this economy-first path.
6. After both owners terminate, launch exactly one
   `orchestrator:sweep-integrator` Agent in main. Give it only usable writing
   commits, declared path scopes, the common base SHA, and the union of focused
   checks. It must inspect and cherry-pick commits serially in frontier order,
   stop on any conflict or unexpected path, and return `status`,
   `integratedCommits`, resulting HEAD, changed paths, conflicts, and checks.
   Read-only owner evidence bypasses Git integration.
7. Invoke `orchestrator:fugu-frontier-final` once with the workspace,
   integration result, and both items. Each item contains its issue ID,
   resolved task, exact acceptance array, `writes`, security flag, route
   assignments, and owner result. The workflow runs one independent checker
   per Bead in parallel and applies a deterministic exact-criterion gate. It
   does not buy a standing research or judge panel and performs no repair.
8. Checkpoint the two Beads one at a time with their separate workflow run IDs.
   Build each queue from its owner and checker with real persona, model,
   status, evidence, and route attempt. Use `accept` only for that item's
   deterministic acceptance; otherwise use `revise` for a task-level failure
   or `inconclusive` for infrastructure failure. A failed sibling never
   downgrades an accepted independent Bead. Checkpoint order follows frontier
   order so Beads history and lease release are deterministic.
9. Apply the evidence-admission policy below separately to each checkpointed
   Bead. A sibling's evidence cannot create work under the other Bead.
10. Report both Bead outcomes, commits, integration checks, checker routes, and
   smallest remaining blockers. Then stop. The next `continue` reranks the
   frontier from the newly persisted state rather than recursing in one
   context.

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
11. After checkpointing, apply the evidence-admission policy below to concrete
   owner or checker discoveries. Admission failure does not change the run's
   verdict and must not be retried informally.
12. Report the judgment, stop reason, queue totals, routed models, and real
   verification results. A blocked, rejected, no-progress, round-limited, or
   inconclusive result is not success.

## Evidence Admission

Do not turn every `nextAction`, hypothesis, review suggestion, or possible bug
into a Bead. Call `mcp__plugin_orchestrator_fugu__admit_discoveries` only when
the returned run evidence supports at most four durable discoveries for that
source Bead. The MCP serializes all writes, suppresses duplicates, and records
an audit comment. Use one of these contracts:

```json
{
  "kind": "issue",
  "title": "durable and specific title",
  "description": "observed problem or deliverable and why it matters",
  "durable_reason": "deliverable|reproducible-blocker|independently-actionable-investigation",
  "acceptance_criteria": ["exact observable completion condition"],
  "reproducible_check": "bounded command or device procedure",
  "evidence": [{"type": "artifact|command|test|device|log", "source": "path or command", "observation": "concrete observed result"}],
  "issue_type": "bug|feature|task|chore",
  "priority": 2
}
```

```json
{
  "kind": "dependency",
  "issue_id": "blocked Bead",
  "depends_on_id": "required Bead",
  "confidence": "high",
  "blocked_criterion": "exact criterion that cannot advance",
  "reproducible_check": "bounded check demonstrating the dependency",
  "evidence": [{"type": "artifact|command|test|device|log", "source": "path or command", "observation": "concrete observed result"}]
}
```

Dependency hypotheses from frontier planning are never sufficient by
themselves. Promote one only after owner or checker evidence demonstrates the
blocked criterion. Rejected admissions remain ephemeral run evidence; do not
weaken the contract or bypass the MCP.

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
