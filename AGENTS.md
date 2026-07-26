# Agent Instructions

- Claude Code native dynamic workflows are the only agent scheduler.
- Keep Fugu limited to persona/model selection; it must never launch workers.
- Preserve the append-only evidence board: corrections are new messages, never
  rewrites.
- Treat model personality scores as calibrated priors, not facts. Preserve
  provenance and confidence, and prefer measured outcomes over reputation.
- Never fabricate provider output or substitute a mock for a live model call.
  Unit tests may isolate local process boundaries, but live smoke tests must use
  the real configured provider.
- A worker returning is not completion. Require criterion-level evidence and
  the deterministic acceptance gate.
- Keep agent calls bounded and stop on rejection, no progress, or round limits.
- Optimize for accepted progress per model call. Default to quick forums,
  8-unit/4-slot sweeps, one final audit plus an independent judge, and at most
  two declared route attempts. Escalate only for explicit high assurance.
- Across the portfolio, run paid agent work in at most two project sessions at
  once and only one high-assurance/full/UltraCheck workflow at a time.
- Serialize Beads writes and close an issue only after accepted evidence.
- Run `uv run pytest -q`, `node --check
  claude-plugin/workflows/fugu-forum.js`, and `claude plugin validate
  claude-plugin` before publication.
