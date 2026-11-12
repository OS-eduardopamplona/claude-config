input=$(cat)
case "$input" in
  *sed*) ;;
  *) exit 0 ;;
esac
cmd=$(printf '%s' "$input" | sed -nE 's/.*"command" *: *"((\\.|[^"\\])*)".*/\1/p')
set -f
while IFS= read -r seg; do
  printf '%s' "$seg" | grep -qE '(^|[[:space:]/])sed[[:space:]]' || continue
  args=${seg#*sed }
  inplace=0
  binary=0
  for tok in $args; do
    case "$tok" in
      --in-place*) inplace=1 ;;
      --binary) binary=1 ;;
      --*) ;;
      -*)
        flags=${tok#-}
        case "$flags" in
          *i*) inplace=1; flags=${flags%%i*} ;;
        esac
        case "$flags" in *b*) binary=1 ;; esac
        ;;
    esac
  done
  if [ "$inplace" = 1 ] && [ "$binary" = 0 ]; then
    printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Git Bash sed -i rewrites CRLF line endings as LF. Add -b to keep them (sed -i -b ...), or use the Edit tool."}}'
    exit 0
  fi
done <<< "$(printf '%s' "$cmd" | sed -E 's/\\n/\n/g; s/(&&|\|\||[;|&])/\n/g')"
exit 0
