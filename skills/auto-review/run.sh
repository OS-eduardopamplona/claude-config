#!/usr/bin/env bash
S=C:/Users/U005017/.claude/skills/auto-review
LOGS=/c/Users/U005017/.claude/auto-review/logs
export PATH="/c/Users/U005017/.local/bin:$PATH"
ar() { node "$S/auto-review.mjs" "$@"; }
[[ "$*" == *#* || "$*" == */pull/* ]] && exec bash "$S/now.sh" "$@"
mkdir -p "$LOGS"
find "$LOGS" -name '*.jsonl' -mtime +14 -delete
cd /c/git/OutSystems.ModelExtensions || exit 1
ar lock --claims || exit 0
me=$(cat /proc/$$/winpid)
export AUTO_REVIEW_CLAIM_PID=$me
tried="$LOGS/../tried-$$.txt"
trap 'rm -f "$tried"; ar release --pid "$me"; ar unlock' EXIT
: >"$tried"

review() {
  local log=$1
  shift
  echo "log: $log"
  AUTO_REVIEW_LOCKED=1 claude -p "Read $S/SKILL.md and follow it. Args: $*" --model opus --settings "$S/settings.json" --permission-mode bypassPermissions --output-format stream-json --verbose </dev/null >"$log" 2>&1
}

while :; do
  ar lock --renew --claims
  batch=$(ar next --exclude "$tried") || { echo "selection failed"; break; }
  [ -z "$batch" ] && { echo "nothing left due"; break; }
  awk '{ print $1 "@" $2 }' <<<"$batch" >>"$tried"
  claimed=$(ar claim --pid "$me" $(awk '{ print $1 }' <<<"$batch"))
  [ -z "$claimed" ] && continue
  logs=()
  while read -r pr slot; do
    log="$LOGS/$(date +%Y%m%d-%H%M%S)-$(tr '/#' '--' <<<"${pr#*/}").jsonl"
    logs+=("$log")
    review "$log" "$@" "slot=$slot" "$pr" &
  done <<<"$claimed"
  wait
  ar release --pid "$me"
  failed=0
  for log in "${logs[@]}"; do ar check-run "$log" || failed=1; done
  [ "$failed" = 0 ] || { echo "stopping"; break; }
done
