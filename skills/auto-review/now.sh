#!/usr/bin/env bash
S=C:/Users/U005017/.claude/skills/auto-review
LOGS=/c/Users/U005017/.claude/auto-review/logs
export PATH="/c/Users/U005017/.local/bin:$PATH"
ar() { node "$S/auto-review.mjs" "$@"; }
prs=()
opts=()
for a in "$@"; do
  case $a in
    *#* | */pull/*) prs+=("$a") ;;
    *) opts+=("$a") ;;
  esac
done
[ ${#prs[@]} -gt 0 ] || { echo "usage: now.sh [dry-run] [no-red-green] <owner/repo#n | PR url>..."; exit 2; }
mkdir -p "$LOGS"
cd /c/git/OutSystems.ModelExtensions || exit 1
me=$(cat /proc/$$/winpid)
export AUTO_REVIEW_CLAIM_PID=$me
trap 'ar release --pid "$me"' EXIT
claimed=$(ar claim --pid "$me" "${prs[@]}") || exit 1
[ -n "$claimed" ] || { echo "nothing to start: every PR named is being reviewed by another run"; exit 0; }

review() {
  local log=$1
  shift
  AUTO_REVIEW_LOCKED=1 claude -p "Read $S/SKILL.md and follow it. Args: $*" --model opus --settings "$S/settings.json" --permission-mode bypassPermissions --output-format stream-json --verbose </dev/null >"$log" 2>&1
}

jobs=()
while read -r pr slot; do
  log="$LOGS/$(date +%Y%m%d-%H%M%S)-now-$(tr '/#' '--' <<<"${pr#*/}").jsonl"
  echo "$pr: slot $slot, log $log"
  (
    review "$log" "${opts[@]}" "slot=$slot" "$pr"
    ar check-run "$log" --now
    rc=$?
    ar release --pid "$me" "$pr"
    echo "$pr: $([ "$rc" = 0 ] && echo finished || echo failed), log $log"
    exit $rc
  ) &
  jobs+=($!)
done <<<"$claimed"
failed=0
for j in "${jobs[@]}"; do wait "$j" || failed=1; done
exit $failed
