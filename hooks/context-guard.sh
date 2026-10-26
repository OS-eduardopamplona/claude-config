#!/usr/bin/env bash
transcript=$(jq -r '.transcript_path // empty')
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
  msg="Context guard: conversation is at ~${k}K tokens (handoff threshold ${handoff}). Do not start new work. Finish or pause the current step, write a handoff per the context rule, and recommend the user continue in a fresh session."
elif [ "$tokens" -ge "$warn" ]; then
  msg="Context guard: conversation is at ~${k}K tokens (warn threshold ${warn}). Delegate wide searches to subagents. If the user starts a new or unrelated task, recommend a handoff and a fresh session first."
else
  exit 0
fi

jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"UserPromptSubmit",additionalContext:$m}}'
