# Context Budget

Auto-compact fires at 400K (`autoCompactWindow` in `settings.json`).

- Delegate wide searches and multi-file reading to subagents; keep their results, not file dumps.

# Compact instructions

Preserve: the task goal, decisions Eduardo made, failed approaches, files changed, remaining steps, and for an orchestrator each linked child session's `local_…` id, purpose and state. Drop tool output and file contents that can be re-read.
