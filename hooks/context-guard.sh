#!/usr/bin/env bash
input=$(cat)
transcript=$(jq -r '.transcript_path // empty' <<<"$input")
event=$(jq -r '.hook_event_name // "UserPromptSubmit"' <<<"$input")
session=$(jq -r '.session_id // empty' <<<"$input")
[ -f "$transcript" ] || exit 0

tokens=$(tail -n 400 "$transcript" \
  | jq -c 'select(.isSidechain != true) | .message.usage? // empty' 2>/dev/null \
  | tail -n 1 \
  | jq '(.input_tokens // 0) + (.cache_creation_input_tokens // 0) + (.cache_read_input_tokens // 0)' 2>/dev/null)
[ -n "$tokens" ] || exit 0

warn=${CONTEXT_GUARD_WARN:-140000}
handoff=${CONTEXT_GUARD_HANDOFF:-180000}
k=$((tokens / 1000))

if [ "$tokens" -ge "$handoff" ]; then
  level=handoff
  msg="Context guard: conversation is at ~${k}K tokens (handoff threshold ${handoff}). Do not start new work. Finish or pause the current step, then do the automatic handoff from the context rule: write the handoff file and start a fresh session from it."
elif [ "$tokens" -ge "$warn" ]; then
  level=warn
  msg="Context guard: conversation is at ~${k}K tokens (warn threshold ${warn}). Delegate wide searches to subagents. If the user starts a new or unrelated task, recommend a handoff and a fresh session first."
else
  exit 0
fi

if [ "$event" = "PostToolUse" ] && [ -n "$session" ]; then
  state="$HOME/.claude/hooks/.state/$session"
  [ "$(cat "$state" 2>/dev/null)" = "$level" ] && exit 0
  mkdir -p "${state%/*}"
  echo "$level" > "$state"
fi

jq -n --arg e "$event" --arg m "$msg" '{hookSpecificOutput:{hookEventName:$e,additionalContext:$m}}'
