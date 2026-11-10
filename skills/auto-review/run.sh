#!/usr/bin/env bash
S=C:/Users/U005017/.claude/skills/auto-review
LOGS=/c/Users/U005017/.claude/auto-review/logs
export PATH="/c/Users/U005017/.local/bin:$PATH"
ar() { node "$S/auto-review.mjs" "$@"; }
mkdir -p "$LOGS"
find "$LOGS" -name '*.jsonl' -mtime +14 -delete
cd /c/git/OutSystems.ModelExtensions || exit 1
ar lock || exit 0
trap 'ar unlock' EXIT

review() {
  log="$LOGS/$(date +%Y%m%d-%H%M%S).jsonl"
  echo "log: $log"
  AUTO_REVIEW_LOCKED=1 claude -p "Read $S/SKILL.md and follow it. Args: $*" --model opus --settings "$S/settings.json" --permission-mode bypassPermissions --output-format stream-json --verbose >"$log" 2>&1
  ar check-run "$log" || { echo "stopping"; return 1; }
}

if [[ "$*" == *#* ]]; then
  review "$@"
  exit
fi

tried="$LOGS/../tried-$$.txt"
trap 'rm -f "$tried"; ar unlock' EXIT
: >"$tried"
while :; do
  ar lock --renew
  batch=$(ar next --exclude "$tried") || { echo "selection failed"; break; }
  [ -z "$batch" ] && { echo "nothing left due"; break; }
  awk '{ print $1 "@" $2 }' <<<"$batch" >>"$tried"
  review "$@" $(awk '{ print $1 }' <<<"$batch") || break
done
