# Native Workflow Examples

Every example below launches the same saved `orchestrator:fugu-forum` workflow.
Fugu changes route assignments; it does not create a second execution graph.
Inspect and control the run with `/workflows`.

## Quick Evidence Gate

```text
/orchestrator:orchestrate Use a quick workflow to inspect README.md and report
its exact H1 with direct file evidence and independent criterion-level judgment.
Do not edit files.
```

Quick mode omits competing opening hypotheses and cross-examination. It still
runs the routed researcher, one real artifact worker, an independent verifier,
and the deterministic judge. Use it for bounded checks where the full forum
would add cost without materially improving the answer.

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

Ask Claude Code to inspect `bd ready --json`, choose the intended issue, and
invoke `/orchestrator:orchestrate bead=<id> ...`. Dependency ordering belongs to
Beads. Parallel agent scheduling for the claimed issue belongs to `/workflows`.

## Future Provider Adapter

A future K3 route follows the existing Codex pattern:

1. Add the logical model to the active route catalog and persona preferences.
2. Map its provider family to one bounded native adapter agent.
3. Have that adapter make exactly one real provider call and return the required
   structured envelope.
4. Add fallback and routing evidence.

The Fugu policy and native queue do not change. The adapter is a worker
transport, never another scheduler.
