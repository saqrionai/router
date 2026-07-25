# Orchestrator Fugu Claude Plugin

This plugin makes Claude Code's dynamic workflow runtime the interactive
execution plane for Orchestrator.

- `/orchestrator:orchestrate <task>` asks Fugu to route personas, then launches
  the native `orchestrator:fugu-forum` workflow.
- `/workflows` shows phases, agents, prompts, tool activity, tokens, and results.
- Opus 5 handles native research, security analysis, and synthesis.
- Fable 5 is restricted to neutral, non-security research, verification, and
  judgment. Security tasks exclude Fable because its provider can silently
  fall back to Opus when supplied security evidence.
- GPT-5.6 is reached through the real `codex-subagent` CLI adapter.
- Beads is the durable outer queue; the workflow returns its in-run queue and
  closes a Bead only after criterion-level acceptance.
- Revision waves stop on acceptance, rejection, repeated no-progress, or the
  configured round budget.
- Lifecycle hooks append native subagent events to
  `~/.local/state/orchestrator/claude-native-events.jsonl`.

Claude Code's native workflow runtime is the only scheduler. Python provides the
Fugu routing MCP and read-only historical telemetry; it does not launch agents.

See `examples/README.md` for native normal, UltraCheck, queued-Bead, and future
provider-adapter examples.
