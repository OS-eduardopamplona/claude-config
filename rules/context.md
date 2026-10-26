# Context Budget

A UserPromptSubmit hook (`hooks/context-guard.sh`) injects a "Context guard" note when the conversation passes ~140K tokens (warn) or ~180K (handoff). Auto-compact fires at 200K.

- Delegate wide searches and multi-file reading to subagents; keep their results, not file dumps.
- On a warn note: finish the current step; if Eduardo starts a new or unrelated task, recommend a handoff and a fresh session before starting it.
- On a handoff note, first check `mcp__ccd_session_mgmt__list_sessions` with `{"linked": true}`. If this session has linked children (an orchestrator), do not hand off: a fresh session would not be their parent and would miss their completion notes. Start no new work, finish the current step, and tell Eduardo to run `/compact` (auto-compact at 200K does it anyway).
- Otherwise, on a handoff note: start no new work. Write `~/.claude/handoffs/<repo>-<branch>.md` (goal, done, decisions, failed approaches, next steps, files touched; under 500 words). This is a standing request from Eduardo to hand off automatically: if `start_session` is available (Claude desktop app), call it with `context: "fresh"`, `initiation: "user_asked"`, and the brief "Read the handoff at <path> and continue", then stop working here and link the new session. Otherwise tell Eduardo to open a fresh session with "read the handoff at <path>".
- When resuming from a handoff, read it first and delete it once its next steps are done.

# Compact instructions

Preserve: the task goal, decisions Eduardo made, failed approaches, files changed, remaining steps, and for an orchestrator each linked child session's `local_…` id, purpose and state. Drop tool output and file contents that can be re-read.
