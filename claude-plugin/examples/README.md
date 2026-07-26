# Native Workflow Examples

The plugin has two native topologies. `fugu-forum` builds one artifact through
bounded adversarial review. Sweep uses the saved `fugu-sweep` read-only planner,
direct native worktree Agents for dependency-ready implementation units, and
the saved `fugu-sweep-final` audit. Fugu changes persona/model assignments; it
does not launch agents or create another daemon.

## Large Project Sweep

```text
/orchestrator:sweep Continue the current software-engineering project. Build a
validated dependency graph from the active Bead and repository state, run
independent units in parallel worktrees, verify by risk, and integrate only
passing scoped commits. Do not push.
```

The planner queues at most 8 units by default with weighted active capacity 4.
An explicit large sweep permits 24/6; an explicit 64-unit request permits 64/8.
Owners get task-specific personas and Fugu routes. Critical and high-risk units
always get independent review; medium and low risk use deterministic cohort
sampling. A serial integrator stops on dirty state, unexpected paths,
conflicts, or failed checks.
Planning and final audit appear in `/workflows`; owner waves and reviewers
appear in Claude Code's native agent and task views.

## Quick Evidence Gate

```text
/orchestrator:orchestrate Use a quick workflow to inspect README.md and report
its exact H1 with direct file evidence and independent criterion-level judgment.
Do not edit files.
```

Quick mode runs one artifact owner and one independent criterion checker, with
no standing research panel. The owner gathers evidence as needed. A clean run
ends after those two calls; an actionable checker failure permits one targeted
owner/checker revision. This is the economy-first default for a substantial
single artifact.

## Standard Forum

```text
/orchestrator:orchestrate Implement the parser change and independently verify
the regression test and relevant suite.
```

Standard mode is explicit. It runs two opening agents in parallel, one
artifact writer after that evidence barrier, and two independent verification
agents in parallel before judgment. One evidence-backed revision is allowed,
for six calls normally and at most ten.

## Full Forum

```text
/orchestrator:orchestrate full forum: investigate the contradictory crash
evidence, implement the strongest fix, and adversarially verify it.
```

Full mode adds two parallel cross-examiners and permits at most two revision
waves. Use it for ambiguous or high-stakes work, not routine continuation.

## Mixed Anthropic And OpenAI

```text
/orchestrator:orchestrate Implement the parser change in this repository.
Acceptance: the regression test fails before the fix and passes after it; the
relevant suite passes; an independent verifier maps each completion claim to
command or artifact evidence.
```

The normal quality route uses Opus for high-volume analysis and may route
engineering or independent judgment to GPT-5.6 through `codex-worker`. Codex
returns one bounded result to the native workflow; it does not schedule agents.

## UltraCheck

```text
/orchestrator:orchestrate ultracheck the authorization boundary change.
Acceptance: all authorization tests pass from a clean process; the full
applicable test, build, typecheck, and lint checks pass; hostile boundary inputs
are covered; every completion claim has direct evidence.
```

`ultracheck` activates structural gates for broad checks, a clean rerun, at least
five refutation hypotheses, hostile-input categories, and a claim-level evidence
ledger. A judge cannot override missing fields with a confident summary.

## Durable Beads Queue

```text
/orchestrator:orchestrate bead=ios-123 Complete the next accepted unit for this
Bead. Preserve its target boundary and acceptance criteria. Stop as no-progress
if two revision waves add no criterion-level evidence.
```

The skill claims the Bead before launching the native workflow. The workflow
maintains a visible queue of routed units. After it returns, the skill appends
one serialized checkpoint and closes the Bead only for an accepted judgment.
Interrupted workflow execution is resumed by Claude Code; Beads remains project
history rather than an agent chat bus.

## Ready Queue Item

```text
/orchestrator:orchestrate continue
```

The skill automatically resumes the highest-priority in-progress item or claims
the highest-priority dependency-ready item. Priority ties use the most recent
update and then the issue ID. A process lease makes another live client skip the
same Bead. Dependency ordering belongs to Beads; parallel agent scheduling for
the claimed item belongs to `/workflows`.

## Future Provider Adapter

A future K3 route follows the existing Codex pattern:

1. Add the logical model to the active route catalog and persona preferences.
2. Map its provider family to one bounded native adapter agent.
3. Have that adapter make exactly one real provider call and return the required
   structured envelope.
4. Add fallback and routing evidence.

The Fugu policy and native queue do not change. The adapter is a worker
transport, never another scheduler.
