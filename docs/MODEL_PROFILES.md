# Model Profiles

Behavioral profiles are low-confidence routing priors, not vendor benchmarks.
Effective scoring shrinks every trait toward neutral according to
`profile_confidence`; live terminal outcomes and structured-output reliability
gradually calibrate the Fugu router.

## Active Routes

| Route | Backend | Role |
| --- | --- | --- |
| `opus-5[1m]` | Native Claude Code | Full-context interactive or tool-enabled worker |
| `opus-5-bounded` | Native Claude Code | Primary researcher, hypothesis, exploit, and engineering worker |
| `fable-5[1m]` | Native Claude Code | Full-context neutral reviewer |
| `fable-5-bounded` | Native Claude Code | Independent neutral researcher, verifier, or judge |
| `gpt-5.6-high` | Codex | Implementation and first review |
| `gpt-5.6-sol` | Codex | Maximum-reasoning verification and adjudication |
| `gpt-5.6-research` | Codex | Bounded research and source synthesis |

`config/models.json` is the sole active route catalog. A route that is absent
from that file cannot be selected by the composer, Fugu router, or native
plugin.

## Current Composition

For a reverse-engineering and security-research task, policy currently favors:

| Role | Primary route |
| --- | --- |
| Researcher | `opus-5-bounded` |
| Hypothesis generator | `opus-5-bounded` |
| Exploit analyst | `opus-5-bounded` |
| Engineer | `gpt-5.6-high` |
| Verifier | `fable-5-bounded` |
| Judge | `gpt-5.6-sol` |

Fable is limited to neutral evidence work on cybersecurity tasks. It cannot be
assigned as the hypothesis generator, exploit analyst, or implementation
engineer. GPT routes are used where provider independence or Codex's engineering
strength justifies the smaller OpenAI allowance. Opus 5 carries the high-volume
work under the Anthropic subscription.

## Learning Loop

Each native workflow checkpoint records the routed unit, model, outcome, task,
and round. Fugu rebuilds its deterministic reward head from those attributable
results. `orch route PERSONA --task "..."` shows the resulting distribution and
observation counts. Archived pre-native runs remain readable but cannot launch
work. Profile changes must retain provenance and confidence; a handful of
anecdotes must not become a permanent model ranking.
