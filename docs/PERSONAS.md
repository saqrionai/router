# Personas

Personas are epistemic jobs, not cosmetic system prompts. Each has a distinct
failure mode, output contract, trait-weight vector, and candidate model set. The
team composer assigns models jointly so one family does not generate, verify,
and judge its own claims.

| Persona | Primary job | Default route | Main failure checked by others |
| --- | --- | --- | --- |
| Researcher | Build primary evidence and identify missing artifacts | `opus-5-bounded` | Source dumping without a falsifiable conclusion |
| Bullshitter | Generate unusual, high-upside hypotheses | `opus-5-bounded` | Imagination presented as observation |
| Exploiter | Develop authorized, preconditioned security analysis | `opus-5-bounded` | Plausible primitives presented as demonstrated chains |
| Engineer | Turn claims into small experiments, tooling, or fixes | `gpt-5.6-high` | Implementation confidence without repository or test evidence |
| Verifier | Falsify claims and interpret machine results | `fable-5-bounded` | Treating a passing check as proof of more than it covers |
| Judge | Resolve claims based on evidence, not consensus | `gpt-5.6-sol` | Rewarding verbosity, confidence, or circular peer citation |

Every persona returns the same base JSON envelope: summary, typed claims,
evidence, risks, next actions, and verification requests. The judge adds a final
decision and claim disposition. Unstructured output is retained but marked so it
cannot silently look equivalent to a schema-valid result.

The model column shows the current composed default, not a hard binding. Trait
weights and candidates live in `config/personas.json`; model priors live in
`config/models.json`; team constraints live in `config/team-policy.json`.
Changing any of them does not rewrite the workflow or historical messages.
For security-classified tasks, policy removes Fable from every persona before
composition; the verifier then defaults to Opus 5, with Opus 4.8 available only
as a quality-gated recovery route.
