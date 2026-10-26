# Context Budget

A UserPromptSubmit hook (`hooks/context-guard.sh`) injects a "Context guard" note when the conversation passes ~140K tokens (warn) or ~180K (handoff). Auto-compact fires at 200K.

- Delegate wide searches and multi-file reading to subagents; keep their results, not file dumps.
- On a warn note: finish the current step; if Eduardo starts a new or unrelated task, recommend a handoff and a fresh session before starting it.
- On a handoff note: start no new work. Write `~/.claude/handoffs/<repo>-<branch>.md` (goal, done, decisions, failed approaches, next steps, files touched; under 500 words), then tell Eduardo to open a fresh session with "read the handoff at <path>".
- When resuming from a handoff, read it first and delete it once its next steps are done.

# Compact instructions

Preserve: the task goal, decisions Eduardo made, failed approaches, files changed, and remaining steps. Drop tool output and file contents that can be re-read.
