#!/usr/bin/env bash
{
  [ -n "$CLAUDE_PID" ] || exit 0
  dir="$HOME/.claude/telemetry/pids"
  mkdir -p "$dir"
  tmp="$dir/.$CLAUDE_PID.$$.tmp"
  jq -cRs --argjson pid "$CLAUDE_PID" \
    --arg cli "${CLAUDE_CODE_SESSION_ID:-}" \
    --arg host "${CLAUDE_CODE_HOST_SESSION_ID:-}" \
    --arg pwd "$PWD" \
    '. as $raw | {pid:$pid,cli_session:$cli,host_session:(if $host=="" then null else $host end),cwd:(($raw | (try fromjson catch {}) | .cwd? // "") | if . == "" then $pwd else . end),seen_at:(now | (floor | strftime("%Y-%m-%dT%H:%M:%S")) + "." + ((. * 1000 | floor) % 1000 | tostring | ("00" + .)[-3:]) + "Z")}' >"$tmp" \
    && mv -f "$tmp" "$dir/$CLAUDE_PID.json"
  rm -f "$tmp"
} >/dev/null 2>&1
exit 0
