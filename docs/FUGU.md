# Fugu Router

Orchestrator borrows the public routing idea from Sakana AI's Fugu work. It
does not claim to reproduce proprietary model weights, training data, or
checkpoints.

## Product Boundary

Fugu is a policy service inside the Claude Code plugin:

1. `route_team` receives the exact task and the six-person routing roster.
2. The router ranks active model candidates for each persona.
3. It returns logical model ids, native agent types, reasons, and bounded
   fallback orders.
4. Claude Code's native `fugu-forum` workflow executes the selected queue.
5. `checkpoint_bead` records terminal per-unit outcomes for future routing.
6. `admit_discoveries` may persist a bounded evidenced issue or dependency;
   routing hypotheses alone cannot mutate Beads.

Fugu never launches a worker, creates a second execution graph, or manages a
retry loop.

## Route Score

The local router combines:

```text
0.45 * calibrated role/task/capacity prior
+ 0.20 * beta-smoothed terminal success
+ 0.10 * beta-smoothed structured-output success
+ 0.20 * task-conditioned learned reward
+ 0.05 * bounded exploration
```

The task-conditioned head uses a stable hashing encoder and one regularized
logistic head per persona/model route. Predictions shrink toward neutral until
enough attributable native outcomes exist. The model is rebuilt
deterministically from the local append-only ledger.

`family_budget_bias` reflects available subscription capacity. Anthropic is the
default high-volume family; OpenAI is a specialist and independence route.
Measured outcomes can override that prior.

## Security Routing

Fable 5 is used only for neutral, non-security work. Native canary testing
showed that supplied cybersecurity context caused a provider fallback to Opus
5 even under a neutral reviewer contract, which breaks route attribution. For
security tasks Fable cannot be selected for any persona. The native agent
prompt remains a defense-in-depth boundary if a stale route reaches it.
An authorization-required workflow is security-classified by construction; it
does not depend on the user repeating words such as `security` or
`vulnerability` in every task.
The separate `general-forum` is the native path for clearly non-security work
and keeps Fable eligible for neutral verification and judgment.

Only routes in `config/models.json` are active. The current set is Opus 5,
Fable 5, and GPT-5.6 variants. A future provider is added as one bounded native
adapter; it does not change the workflow.

## Inspect Routing

```sh
orch team --workflow security-research-forum --task "implement and verify"
orch route engineer --task "implement and debug the parser"
orch route verifier --task "independently falsify the fix" --json
```

These commands are policy inspection only. Model execution occurs exclusively
inside Claude Code's native workflow runtime.
