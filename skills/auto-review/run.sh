#!/usr/bin/env bash
S=C:/Users/U005017/.claude/skills/auto-review
STATE=/c/Users/U005017/.claude/auto-review
LOGS=$STATE/logs
QUEUE=$STATE/requested.txt
export PATH="/c/Users/U005017/.local/bin:$PATH"
ar() { node "$S/auto-review.mjs" "$@"; }

opts=()
prs=()
for a in "$@"; do
  case $a in
    *#* | */pull/*) prs+=("$a") ;;
    dry-run | deep) opts+=("$a") ;;
    *) echo "usage: run.sh [dry-run] [deep] [<owner/repo#n | PR url>...]"; exit 2 ;;
  esac
done
mkdir -p "$LOGS"
find "$LOGS" -name '*.jsonl' -mtime +14 -delete
cd /c/git/OutSystems.ModelExtensions || exit 1
me=$(cat /proc/$$/winpid)

fail() {
  echo "$1"
  ar alert "Auto-review: a review run failed" "$1"
}

claude_run() {
  local log=$1 prompt=$2
  shift 2
  claude -p "$prompt" --model opus "$@" --settings "$S/settings.json" --permission-mode bypassPermissions --output-format stream-json --verbose </dev/null >"$log" 2>&1
  ar check-run "$log"
}

review() {
  local o=" $1 " pr round last dir log verify effort
  read -r pr round last <<<"$2"
  local dry= deep=
  [[ $o == *" dry-run "* ]] && dry=--dry-run
  [[ $o == *" deep "* ]] && deep=--deep
  log="$LOGS/$(date +%Y%m%d-%H%M%S)-$(tr '/#' '--' <<<"${pr#*/}")"
  echo "$pr round $round: reviewing, log $log.jsonl"
  dir=$(ar prepare "$pr" "$round" "$last" $deep) || { fail "$pr: prepare failed"; return 1; }
  claude_run "$log.jsonl" "Read $S/reviewer.md and follow it. Run dir: $dir.${deep:+ Deep.}" &&
    ar validate "$dir/verdict.json" >/dev/null || { fail "$pr: the reviewer failed ($log.jsonl)"; return 1; }
  verify=$(ar needs-verify "$dir")
  if [ "$verify" = skip ]; then
    cp "$dir/verdict.json" "$dir/verified.json"
  else
    effort=()
    [ "$verify" = max ] && effort=(--effort max)
    claude_run "$log-verify.jsonl" "Read $S/verifier.md and follow it. Run dir: $dir.${deep:+ Deep.}" "${effort[@]}" &&
      ar validate "$dir/verified.json" >/dev/null || { fail "$pr: the verifier failed ($log-verify.jsonl)"; return 1; }
  fi
  ar post "$dir" $dry || { fail "$pr: posting failed ($dir)"; return 1; }
  echo "$pr round $round: done"
}

named() {
  local sel
  sel=$(ar next --force "$2") || { fail "$2: selection failed"; return 1; }
  [ -n "$sel" ] || { echo "$2: nothing to review"; return 0; }
  review "$1" "$sel"
}

drain() {
  local taking="$QUEUE.taking" line words
  while [ -s "$QUEUE" ]; do
    mv "$QUEUE" "$taking"
    while read -r line; do
      read -ra words <<<"$line"
      [ ${#words[@]} -gt 0 ] && named "${words[*]:0:${#words[@]}-1}" "${words[-1]}"
    done <"$taking"
    rm -f "$taking"
  done
}

ar lock --pid "$me"
rc=$?
if [ $rc = 3 ]; then
  [ ${#prs[@]} -gt 0 ] || { echo "another run is in progress"; exit 0; }
  for pr in "${prs[@]}"; do
    echo "${opts[*]} $pr" >>"$QUEUE"
    echo "$pr: queued behind the run in progress"
  done
  ar lock --pid "$me" 2>/dev/null || exit 0
  queued=1
elif [ $rc != 0 ]; then
  exit 1
fi
trap 'ar unlock --pid "$me"' EXIT

drain
if [ -n "$queued" ]; then
  :
elif [ ${#prs[@]} -gt 0 ]; then
  for pr in "${prs[@]}"; do
    named "${opts[*]}" "$pr"
    drain
  done
else
  todo=$(ar next) || { fail "selecting due PRs failed"; exit 1; }
  [ -n "$todo" ] || echo "nothing due"
  while read -r line; do
    [ -n "$line" ] || continue
    review "${opts[*]}" "$line" || { echo "stopping"; break; }
    drain
  done <<<"$todo"
fi

while :; do
  ar unlock --pid "$me"
  [ -s "$QUEUE" ] || break
  ar lock --pid "$me" 2>/dev/null || break
  drain
done
