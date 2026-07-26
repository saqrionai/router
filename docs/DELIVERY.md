# Delivery-First Scheduling

Orchestrator advances the project frontier rather than maintaining a standing
panel of personas. The default loop is:

```text
inspect Beads frontier
        |
        v
bounded best-first planner (one low-effort call only when choice exists)
        |
        v
select one issue, or at most two demonstrably independent issues
        |
        v
one owner per issue -> concrete artifact, check, evidence, or typed blocker
        |
        v
conditional independent check -> serialized Beads checkpoint -> rerank
```

The deterministic frontier prefers in-progress work, then Beads priority,
recent updates, and issue ID. The bounded planner may refine that order from
repository evidence, but it cannot claim work, edit files, mutate Beads, or
turn a dependency hypothesis into project history.

## Breadth And Parallelism

Cross-Bead scheduling and within-Bead decomposition are separate:

- Frontier scheduling compares durable Beads and chooses the next delivery
  move. It selects one by default and at most two when write scopes and first
  steps are independent.
- Sweep breaks one large Bead into a dependency DAG of independently ownable
  units. It is used only when one Bead is too broad for a bounded owner.
- A newly observed dependency stays in workflow evidence until it identifies
  concrete affected Beads and a reproducible reason. Durable issue and edge
  admission is a separate serialized operation.

The frontier planner is read-only. One selection follows the economy-first
forum path. Two validated selections are atomically leased and run as one
bounded native delivery wave: direct owners run in parallel, with worktree
isolation mandatory for every writer; one integrator applies usable
commits serially, one independent checker per Bead runs in parallel, and the
coordinator checkpoints each Bead serially. A
failed sibling does not invalidate an independently accepted Bead. The wave
stops after checkpointing; the next `continue` reranks instead of recursing.

## Conditional Capabilities

The owner is the default. Additional personas are admitted by evidence, not by
a fixed topology:

| Signal | Capability |
| --- | --- |
| Next step is unclear because primary evidence is missing | researcher |
| A risky completion claim needs independent falsification | verifier |
| Evidence conflicts or the same approach repeatedly fails | challenger |
| A concrete domain skill is necessary | specialist |
| High-impact evidence remains irreconcilable | judge |

Normal delivery does not buy all five opinions. An agent return, summary, or
new idea is not progress by itself; the progress floor in `ECONOMY.md` still
applies.

## Durable Discovery

Create a Bead only for a durable deliverable, reproducible blocker, or
independently actionable investigation. Add a dependency edge only when the
source issue cannot advance or be accepted without the target issue and the
relationship has concrete evidence. Tentative ideas, possible bugs, and
uncertain dependency guesses remain in native workflow state until verified.
