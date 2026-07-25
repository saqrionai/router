# Model Profiles

Behavioral profiles are low-confidence routing priors, not vendor benchmarks.
Effective scoring shrinks every trait toward neutral according to
`profile_confidence`; live terminal outcomes and structured-output reliability
gradually calibrate the Fugu router.

Policy currently runs in `shadow` mode. Fugu computes and records its
distribution and top recommendation, but learned adjustments and behavioral
trait priors do not select the live team. Eligibility, declared route order,
required capabilities, capacity policy, and provider-independence constraints
remain active. Promotion to `active` is a deliberate policy change after a
representative hand-labeled evaluation and enough attributable judge outcomes.
`orch doctor` warns when a profile source is undated or older than the policy's
freshness threshold.

## Active Routes

| Route | Backend | Role |
| --- | --- | --- |
| `opus-5[1m]` | Native Claude Code | Full-context interactive or tool-enabled worker |
| `opus-5-bounded` | Native Claude Code | Primary researcher, hypothesis, exploit, and engineering worker |
| `opus-4.8-bounded` | Native Claude Code | Recovery-only worker after an objective response-quality failure |
| `fable-5[1m]` | Native Claude Code | Full-context neutral reviewer |
| `fable-5-bounded` | Native Claude Code | Independent neutral researcher, verifier, or judge |
| `codex-sol-high` | Codex | Implementation and first review |
| `gpt-5.6-sol` | Codex | Maximum-reasoning verification and adjudication |
| `codex-sol-medium` | Codex | Bounded research and source synthesis |

`codex-sol-medium` and `codex-sol-high` are Orchestrator profile IDs, not
provider model IDs. They and `gpt-5.6-sol` all invoke the actual
`gpt-5.6-sol` model with `medium`, `high`, and `xhigh` reasoning respectively.
The current local Codex registry reports a 272,000-token model context window;
Orchestrator records that provider value rather than advertising a logical
profile as a separate model.

`config/models.json` is the sole active route catalog. A route that is absent
from that file cannot be selected by the composer, Fugu router, or native
plugin. A route marked `fallback_only` cannot be selected as a team primary.

## Current Composition

For a reverse-engineering and security-research task, policy currently favors:

| Role | Primary route |
| --- | --- |
| Researcher | `opus-5-bounded` |
| Hypothesis generator | `opus-5-bounded` |
| Exploit analyst | `opus-5-bounded` |
| Engineer | `codex-sol-high` |
| Verifier | `opus-5-bounded` |
| Judge | `gpt-5.6-sol` |

Fable is limited to genuinely neutral, non-security work. A live native canary
on 2026-07-24 showed that even a neutral reviewer persona hard-fell back from
Fable 5 to Opus 5 when its supplied evidence contained detailed security
context; retaining that logical route would misattribute usage and outcomes.
Security tasks therefore exclude Fable entirely and use Opus 5, GPT-5.6, and
the Opus 4.8 recovery route. Opus 5 carries the high-volume work under the
Anthropic subscription.

## Degradation Recovery

The native Opus 4.8 route uses the first-party canonical identifier
`claude-opus-4-8`; the former LiteLLM alias `opus-4.8` is not valid first-party.
It appears immediately after the selected primary in each declared fallback
order.

Fallback activates for transport or schema failure and for conservative
deterministic degradation signals: empty or content-free completion, missing
persona-required evidence, supported claims without evidence identifiers,
passed checks without observations, malformed evidence identities, an
unactionable blocked result, criterion drift, or a contradictory judgment.
Disagreement, a negative finding, or a properly evidenced `blocked` result is
not degradation.

Every attempt is recorded in the native queue as `usable`, `unavailable`,
`invalid`, or `degraded`, with exact reasons. This makes recovery visible in
`/workflows`, persists both failed and successful recovery attempts in Beads,
and gives the Fugu learning loop attributable negative and positive outcomes.

## Learning Loop

Each native workflow checkpoint records the routed unit, model, outcome, task,
and round. Fugu rebuilds its deterministic reward head from those attributable
results. `orch route PERSONA --task "..."` shows the resulting distribution and
observation counts. Archived pre-native runs remain readable but cannot launch
work. Profile changes must retain provenance and confidence; a handful of
anecdotes must not become a permanent model ranking.
